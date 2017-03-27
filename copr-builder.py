import argparse
import configparser
import copr
import datetime
import logging
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

from collections import namedtuple
from copr.client_v2.common import BuildStateValues
from distutils.version import LooseVersion

Version = namedtuple('Version', ['version', 'build', 'date', 'git_hash'])


class CoprBuilderError(Exception):
    pass


def run_command(command):
    res = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)

    out, err = res.communicate()
    if res.returncode != 0:
        output = out.decode().strip() + '\n' + err.decode().strip()
    else:
        output = out.decode().strip()
    return (res.returncode, output)


class GitRepo(object):

    def __init__(self, repo_url):
        self.repo_url = repo_url
        self.tempdir = tempfile.TemporaryDirectory()

        self.gitdir = None

    def clone(self):
        command = 'cd %s && git clone %s' % (self.tempdir.name, self.repo_url)
        ret, out = run_command(command)
        if ret != 0:
            raise CoprBuilderError('Failed to clone %s:\n%s' % (self.repo_url, out))

        subdirs = os.listdir(self.tempdir.name)
        if len(subdirs) != 1:
            raise CoprBuilderError('Git directory not found after successful clone.')

        self.gitdir = self.tempdir.name + '/' + subdirs[0]

    def last_commit(self, short=True):
        command = 'cd %s && git log --pretty=format:\'%%%s\' -n 1' % (self.gitdir, 'h' if short else 'H')
        ret, out = run_command(command)
        if ret != 0:
            raise CoprBuilderError('Failed to get last commit hash for %s:\n%s' % (self.repo_url, out))

        return out

    def checkout(self, branch):
        command = 'cd %s && git checkout %s' % (self.gitdir, branch)
        ret, out = run_command(command)
        if ret != 0:
            raise CoprBuilderError('Failed to checkout branch %s:\n%s' % (branch, out))

    def merge(self, branch):
        command = 'cd %s && git merge --ff origin/%s' % (self.gitdir, branch)
        ret, out = run_command(command)
        if ret != 0:
            raise CoprBuilderError('Failed to merge brach %s:\n%s' % (branch, out))


class Project(object):

    def __init__(self, project_data, copr_client):
        self.project_data = project_data
        self.copr_client = copr_client

        self._log_prefix = 'Package %s (repo %s/%s):' % (self.project_data['package'],
                                                         self.project_data['copr_user'],
                                                         self.project_data['copr_repo'])

        self.git_repo = GitRepo(project_data['git_url'])
        self.git_repo.clone()

    def build_srpm(self):
        ''' Build an SRPM package for this project

            returns (str): path to newly created SRPM
        '''
        logging.info('%s New SRPM build started.', self._log_prefix)
        last_build = self._get_last_build_version()

        # checkout to the right branch
        self.git_repo.checkout(self.project_data['git_branch'])

        # and do the merge if we want to
        if 'git_merge_branch' in self.project_data.keys():
            self.git_repo.merge(self.project_data['git_merge_branch'])

        last_commit = self.git_repo.last_commit()
        if last_build and last_commit == last_build.git_hash:
            logging.info('%s Newest version is already built (git hash: %s).', self._log_prefix, last_commit)
            return None

        # make source archive
        archive = self._make_archive()

        # update spec file
        spec = self._update_spec_file(last_build, archive, last_commit)

        # make srpm
        srpm = self._make_srpm(spec, archive)
        return srpm

    @property
    def git_dir(self):
        return self.git_repo.gitdir

    def _extract_version(self, version_str):
        ''' Extract version info from string '''

        # version string looks like '2.33-8.20170322gitcb678c83.fc26'
        version, build = version_str.split('-')
        build_num, git, _dist = build.split('.')
        datestr, git_hash = git.split('git')

        return Version(version, build_num, datestr, git_hash)

    def _get_last_build_version(self):
        ''' Get last package version built in Copr for this project '''

        copr_user = self.project_data['copr_user']
        copr_repo = self.project_data['copr_repo']
        copr_package = self.project_data['package']

        # get the project to extract project id
        plist = self.copr_client.projects.get_list(owner=copr_user, name=copr_repo)
        if len(plist.projects) != 1:
            raise CoprBuilderError('Expected to found exactly one Copr project for %s/%s '
                                   'but found %d' % (copr_user, copr_repo, len(plist.projects)))
        pid = plist.projects[0].id

        # get list of builds for this Copr project
        all_builds = self.copr_client.builds.get_list(owner=copr_user, project_id=pid)
        project_builds = [b for b in all_builds if b.package_name == copr_package and b.state not in ('skipped', 'canceled')]
        if len(project_builds) == 0:
            logging.debug('%s No previous builds found.', self._log_prefix)
            return None  # no previous builds, we are doing the first one

        last = max(project_builds, key=lambda x: x.submitted_on)

        logging.debug('%s Found latest build: %s-%s (ID: %s)', self._log_prefix,
                      last.package_name, last.package_version, last.id)
        return self._extract_version(last.package_version)

    def _make_archive(self):
        ''' Create source archive for this project '''

        logging.debug('%s Started creating source archive.', self._log_prefix)

        command = 'cd %s && %s' % (self.git_dir, self.project_data['archive_cmd'])
        ret, out = run_command(command)
        if ret != 0:
            raise CoprBuilderError('Failed to create source archive for %s:\n%s' % (self.project_data['package'], out))

        # archive should be created, get everything that looks like one
        archives = [f for f in os.listdir(self.git_dir) if re.match(r'.*\.tar\.[gz|bz|bz2]', f)]
        if not archives:
            raise CoprBuilderError('Failed to find source archive after creating it.')
        if len(archives) > 1:
            raise CoprBuilderError('Found more than one file that looks like source archive.')

        logging.debug('%s Created source archive: %s', self._log_prefix, archives[0])

        return archives[0]

    def _locate_spec_file(self):
        ''' Try to find spec file for this project '''

        # look for spec files in current directory and subdirectories
        specs = glob.glob('%s/*.spec' % self.git_dir)
        specs.extend(glob.glob('%s/*/*.spec' % self.git_dir))

        if not specs:
            raise CoprBuilderError('Failed to find a spec file for %s.' % self.project_data['package'])
        if len(specs) > 1:
            raise CoprBuilderError('Found more than one file that looks a spec file.')

        logging.debug('%s Spec found: %s', self._log_prefix, specs[0])

        return specs[0]

    def _new_version(self, spec_version, copr_version, last_commit):
        '''Get new version based on current version in git and last build in Copr '''

        if not copr_version:  # first build in copr
            release = str(int(spec_version.build) + 1)
        elif LooseVersion(spec_version.version) > LooseVersion(copr_version.version):
            release = str(int(spec_version.build) + 1)
        elif LooseVersion(spec_version.version) == LooseVersion(copr_version.version):
            release = str(int(copr_version.build) + 1)
        else:
            raise CoprBuilderError('Version from spec is older than last build in Copr')

        date = datetime.date.today().strftime('%Y%m%d')

        logging.debug('%s New version: %s-%s.%sgit%s', self._log_prefix, spec_version.version, release, date, last_commit)

        return Version(spec_version.version, release, date, last_commit)

    def _get_spec_version(self, spec):
        ''' Get version from spec file '''

        version = None
        release = None

        with open(spec, 'r') as f:
            for line in f:
                if line.startswith('Version:'):
                    version = line.split('Version:')[1].strip()
                elif line.startswith('Release:'):
                    release = line.split('Release:')[1].strip()

                if version and release:
                    break

        if not (version and release):
            raise CoprBuilderError('Failed to extract version and release from spec file %s' % spec)

        release = release.split('%')[0]

        logging.debug('%s Spec version: %s-%s', self._log_prefix, version, release)

        return Version(version, release, None, None)

    def _update_spec_file(self, copr_version, archive_name, last_commit):
        ''' Update version in spec file so the build number is always higher '''

        spec_file = self._locate_spec_file()
        spec_version = self._get_spec_version(spec_file)
        new_version = self._new_version(spec_version, copr_version, last_commit)

        new_spec = []

        with open(spec_file, 'r') as f:
            for line in f:
                if line.startswith('Version:'):
                    new_spec.append('Version: %s\n' % new_version.version)
                elif line.startswith('Release:'):
                    new_spec.append('Release: %s.%sgit%s%%{?dist}\n' % (new_version.build,
                                                                        new_version.date,
                                                                        new_version.git_hash))
                elif line.startswith('Source0:'):
                    new_spec.append('Source0: %s\n' % archive_name)
                else:
                    new_spec.append(line)

        with open(spec_file, 'w') as f:
            for line in new_spec:
                f.write(line)

        logging.debug('%s Spec updated.', self._log_prefix)

        return spec_file

    def _make_srpm(self, spec, archive):
        ''' Create SRPM using spec and source archive '''

        git_dir = self.git_repo.gitdir
        pkg_name = self.project_data['package']

        # copy source archive to rpmbuild/SOURCES
        ret, rpmsource = run_command('rpm -E %_sourcedir')
        if ret != 0:
            raise CoprBuilderError('Failed to get rpmbuild SOURCE directory location.')

        shutil.copyfile('%s/%s' % (git_dir, archive),
                        '%s/%s' % (rpmsource, archive))

        # build the srpm
        command = 'cd %s && rpmbuild -bs %s' % (git_dir, spec)
        ret, out = run_command(command)
        if ret != 0:
            raise CoprBuilderError('SPRM generation failed:\n %s' % out)

        srpm = out.split('Wrote:')[1].strip()
        logging.info('%s SRPM built for %s: %s', self._log_prefix, pkg_name, srpm)
        return srpm


class CoprBuilder(object):

    def __init__(self, conf_file):

        self.config = configparser.ConfigParser()
        self.config.read(conf_file)

        self.copr = copr.create_client2_from_file_config()

    def do_builds(self):
        srpms = {}

        # generate srpms for projects in config
        for project in self.config.sections():
            try:
                p = Project(self.config[project], self.copr)
                srpm = p.build_srpm()
                if srpm:
                    srpms[project] = srpm
            except CoprBuilderError as e:
                logging.error('Failed to create SRPM for %s:\n%s', project, str(e))

        # for all generated srpms run the copr build
        builds = []
        for project in srpms.keys():
            try:
                build = self._do_copr_build(project, srpms[project])
                builds.append(build)
            except CoprBuilderError as e:
                logging.error('Failed to start Copr build for %s:\n%s', project, str(e))

        return self._watch_builds(builds)

    def _do_copr_build(self, project, srpm):
        copr_user = self.config[project]['copr_user']
        copr_repo = self.config[project]['copr_repo']

        # get the project to extract project id
        plist = self.copr.projects.get_list(owner=copr_user, name=copr_repo)
        if len(plist.projects) != 1:
            raise CoprBuilderError('Expected to found exactly one Copr project for %s/%s but '
                                   'found %d' % (copr_user, copr_repo, len(plist.projects)))

        copr_project = plist.projects[0]
        build = copr_project.create_build_from_file(srpm)

        logging.info('Started Copr build of %s (ID: %s)', srpm, build.id)

        return build

    def _watch_builds(self, builds):
        success = True

        while builds:
            for build in builds:
                b = build._handle.get_one(build.id)
                if b.state in (BuildStateValues.SKIPPED, BuildStateValues.FAILED,
                               BuildStateValues.SUCCEEDED, BuildStateValues.CANCELED):
                    logging.info('Build of %s-%s (ID: %s) finished: %s',
                                 b.package_name, b.package_version, b.id, b.state)
                    if b.state == BuildStateValues.FAILED:
                        success = False
                    builds.remove(build)

            time.sleep(0.5)

        return success


if __name__ == '__main__':

    argparser = argparse.ArgumentParser(description='Copr builder')
    argparser.add_argument('-v', '--verbose', action='store_true', help='print debug messages')
    argparser.add_argument('config', nargs=1, help='config file location')
    args = argparser.parse_args()

    if args.verbose:
        logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
    else:
        logging.basicConfig(stream=sys.stderr, level=logging.INFO)

    builder = CoprBuilder(args.config)
    suc = builder.do_builds()

    sys.exit(0 if suc else 1)
