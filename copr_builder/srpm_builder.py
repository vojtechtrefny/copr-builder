import glob
import logging
import os
import re
import shutil

from . import GIT_URL_CONF, PACKAGE_CONF, ARCHIVE_CMD_CONF, GIT_BRANCH_CONF, GIT_MERGE_BRANCH_CONF, Version
from .errors import SRPMBuilderError
from .git_repo import GitRepo
from .utils import run_command


log = logging.getLogger("copr.builder")


class SRPMBuilder(object):

    def __init__(self, project_data):

        self.project_data = project_data

        self._spec_file = None

        self.git_repo = GitRepo(project_data[GIT_URL_CONF])
        self.git_repo.clone()

        self._log_prefix = 'Package %s:' % self.project_data[PACKAGE_CONF]

    @property
    def git_dir(self):
        return self.git_repo.gitdir

    @property
    def spec_file(self):
        if self._spec_file is None:
            self._spec_file = self._locate_spec_file()
        return self._spec_file

    @property
    def spec_version(self):
        ''' Get version from spec file '''

        version = None
        release = None
        spec = self._locate_spec_file()

        with open(spec, 'r') as f:
            for line in f:
                if line.startswith('Version:'):
                    version = line.split('Version:')[1].strip()
                elif line.startswith('Release:'):
                    release = line.split('Release:')[1].strip()

                if version and release:
                    break

        if not (version and release):
            raise SRPMBuilderError('Failed to extract version and release from spec file %s' % spec)

        release = release.split('%')[0]

        log.debug('%s Spec version: %s-%s', self._log_prefix, version, release)

        return Version(version, release, None, None)

    @spec_version.setter
    def spec_version(self, new_version):
        ''' Update version in spec file so the build number is always higher '''

        spec_file = self._locate_spec_file()

        new_spec = []

        with open(spec_file, 'r') as f:
            for line in f:
                if line.startswith('Version:'):
                    new_spec.append('Version: %s\n' % new_version.version)
                elif line.startswith('Release:'):
                    new_spec.append('Release: %s.%sgit%s%%{?dist}\n' % (new_version.build,
                                                                        new_version.date,
                                                                        new_version.git_hash))
                else:
                    new_spec.append(line)

        with open(spec_file, 'w') as f:
            for line in new_spec:
                f.write(line)

        log.debug('%s Spec version updated.', self._log_prefix)

    def prepare_build(self):
        # checkout to the right branch
        self.git_repo.checkout(self.project_data[GIT_BRANCH_CONF])

        # and do the merge if we want to
        if GIT_MERGE_BRANCH_CONF in self.project_data.keys():
            self.git_repo.merge(self.project_data[GIT_MERGE_BRANCH_CONF])

    def build(self):
        archive = self._make_archive()
        srpm = self._make_srpm(archive)

        return srpm

    def _set_source(self, archive_name):
        spec_file = self._locate_spec_file()

        new_spec = []

        with open(spec_file, 'r') as f:
            for line in f:
                if line.startswith('Source0:'):
                    new_spec.append('Source0: %s\n' % archive_name)
                else:
                    new_spec.append(line)

        with open(spec_file, 'w') as f:
            for line in new_spec:
                f.write(line)

        log.debug('%s Spec source updated.', self._log_prefix)

    def _make_archive(self):
        ''' Create source archive for this project '''

        log.debug('%s Started creating source archive.', self._log_prefix)

        command = str(self.project_data[ARCHIVE_CMD_CONF])
        ret, out = run_command(command, self.git_dir)
        if ret != 0:
            raise SRPMBuilderError('Failed to create source archive for %s:\n%s' % (self.project_data[PACKAGE_CONF], out))

        # archive should be created, get everything that looks like one
        archives = [f for f in os.listdir(self.git_dir) if re.match(r'.*\.tar\.[gz|bz|bz2|xz]', f)]
        if not archives:
            raise SRPMBuilderError('Failed to find source archive after creating it.')
        if len(archives) > 1:
            raise SRPMBuilderError('Found more than one file that looks like source archive.')

        log.debug('%s Created source archive: %s', self._log_prefix, archives[0])

        return archives[0]

    def _make_srpm(self, archive):
        ''' Create SRPM using spec and source archive '''

        git_dir = self.git_repo.gitdir
        pkg_name = self.project_data[PACKAGE_CONF]

        # create 'packaging' directory in gitdir
        rpmdir = os.path.join(self.git_dir, 'packaging')
        if not os.path.exists(rpmdir):
            os.mkdir(rpmdir)

        # build the srpm
        data = {'srcdir': self.git_dir, 'rpmdir': rpmdir, 'spec': self.spec_file}
        command = 'rpmbuild -bs --define "_sourcedir {srcdir}" --define "_specdir {rpmdir}"' \
                  ' --define "_builddir {rpmdir}" --define "_srcrpmdir {rpmdir}"' \
                  ' --define "_rpmdir {rpmdir}" {spec}'.format(**data)
        ret, out = run_command(command, git_dir)

        # remove the source archive, we no longer need it
        os.remove(os.path.join(self.git_dir, archive))

        if ret != 0:
            raise SRPMBuilderError('SPRM generation failed:\n %s' % out)

        srpm = out.split('Wrote:')[1].strip()
        log.info('%s SRPM built for %s: %s', self._log_prefix, pkg_name, srpm)

        return srpm

    def _locate_spec_file(self):
        ''' Try to find spec file for this project '''

        # look for spec files in current directory and subdirectories
        specs = glob.glob('%s/*.spec' % self.git_dir)
        specs.extend(glob.glob('%s/*/*.spec' % self.git_dir))

        if not specs:
            raise SRPMBuilderError('Failed to find a spec file for %s.' % self.project_data[PACKAGE_CONF])
        if len(specs) > 1:
            raise SRPMBuilderError('Found more than one file that looks a spec file.')

        log.debug('%s Spec found: %s', self._log_prefix, specs[0])

        return specs[0]
