import datetime
import logging

from distutils.version import LooseVersion
from copr.v3 import CoprNoResultException

from . import PACKAGE_CONF, COPR_USER_CONF, COPR_REPO_CONF, GIT_URL_CONF, ARCHIVE_CMD_CONF, Version
from .errors import CoprBuilderError, CoprBuilderConfigurationError, CoprBuilderAlreadyFailed, \
    CoprBuilderBrokenGitHash
from .srpm_builder import SRPMBuilder


log = logging.getLogger("copr.builder")


class CoprProject(object):

    def __init__(self, project_data, copr_client):
        self.project_data = project_data
        self.copr_client = copr_client

        self._test_required_config_values()

        self._log_prefix = 'Package %s (repo %s/%s):' % (self.project_data[PACKAGE_CONF],
                                                         self.project_data[COPR_USER_CONF],
                                                         self.project_data[COPR_REPO_CONF])

        self.srpm_builder = SRPMBuilder(self.project_data)

        # get the Copr project
        try:
            self.copr_project = self.copr_client.project_proxy.get(ownername=self.project_data[COPR_USER_CONF],
                                                                   projectname=self.project_data[COPR_REPO_CONF])
        except CoprNoResultException as e:
            raise CoprBuilderError('Copr project %s/%s not found' % (self.project_data[COPR_USER_CONF],
                                                                     self.project_data[COPR_REPO_CONF])) from e

    def _test_required_config_values(self):
        ''' Test if all required configuration values are set properly. '''
        for conf in [PACKAGE_CONF, COPR_USER_CONF, COPR_REPO_CONF, GIT_URL_CONF, ARCHIVE_CMD_CONF]:
            if conf not in self.project_data.keys():
                raise CoprBuilderConfigurationError('Missing \"%s\" value in the configuration!' % conf)

    def _get_package_version(self, build):
        if build.source_package and 'version' in build.source_package.keys():
            return build.source_package['version']

        else:
            raise CoprBuilderError('Cannot extract version from last build. ID: %s' % build.id)

    def _get_chroots_diff_message(self, project, build):
        ret = ''
        in_project = project - build
        in_build = build - project

        if in_project:
            ret += 'New chroots in project:'
            for chroot in in_project:
                ret += ' %s' % chroot
        if in_build:
            ret += 'Chroots in last build no longer in project:'
            for chroot in in_build:
                ret += ' %s' % chroot

        return ret

    def build_srpm(self):
        ''' Build an SRPM package for this project

            returns (str): path to newly created SRPM
        '''
        log.info('%s New SRPM build started.', self._log_prefix)

        # get last build in Copr
        last_build = self._get_last_build()

        # switch branch and do some other things needed before build
        self.srpm_builder.prepare_build()

        # check if we actually need to do the build -- check version and last commit
        last_commit = self.srpm_builder.git_repo.last_commit()

        try:
            if last_build:
                package_version = self._get_package_version(last_build)
                last_version = self._extract_version(package_version)
            else:
                last_version = None
        except CoprBuilderBrokenGitHash:
            log.warning('%s Can\'t read git hash from the last build. Skipping check and sending '
                        'a new build.', self._log_prefix)
            last_version = None

        if last_build and last_version and last_commit == last_version.git_hash:
            proj_chroots = set(self.copr_project.chroot_repos.keys())
            last_chroots = set(last_build.chroots)

            if proj_chroots != last_chroots:
                # always try to rebuild if there is a change in chroots
                log.info('%s Newest version is already built (git hash: %s) but there are different chroots '
                         'enabled for the project -- building anyway.', self._log_prefix, last_commit)
                chroots_diff = self._get_chroots_diff_message(proj_chroots, last_chroots)
                log.debug('%s %s', self._log_prefix, chroots_diff)
            else:
                if last_build.state == 'failed':
                    date = datetime.date.fromtimestamp(last_build.submitted_on).isoformat()
                    log.error('%s Build of the newest version (git hash: %s) was already submitted on '
                              '%s but it failed.', self._log_prefix, last_version.git_hash, date)
                    raise CoprBuilderAlreadyFailed
                else:
                    log.info('%s Newest version is already built (git hash: %s).', self._log_prefix, last_commit)
                    return None

        self.srpm_builder.make_archive()

        # update version in spec file
        self.srpm_builder.spec_version = self._new_version(self.srpm_builder.spec_version,
                                                           last_version, last_commit)

        # make srpm
        srpm = self.srpm_builder.build()
        return srpm

    def _extract_version(self, version_str):
        ''' Extract version info from string '''

        # there might be epoch in the version string, just ignore it
        if ':' in version_str:
            _epoch, version_str = version_str.split(':')

        # version string looks like '2.33-8.20170322gitcb678c83.fc26'
        version, build = version_str.split('-')
        # ignore the dist part (we don't need it and it is not part of the version for newer builds)
        build_num, git = build.split('.')[:2]
        git_split = git.split('git')
        if len(git_split) != 2:
            raise CoprBuilderBrokenGitHash("Git hash can't be found in previous build")

        datestr, git_hash = git_split

        return Version(version, build_num, datestr, git_hash)

    def _get_last_build(self):
        ''' Get last package build built in Copr for this project '''

        copr_user = self.project_data[COPR_USER_CONF]
        copr_package = self.project_data[PACKAGE_CONF]
        copr_project = self.project_data[COPR_REPO_CONF]

        # get list of builds for this Copr project
        all_builds = self.copr_client.build_proxy.get_list(ownername=copr_user,
                                                           projectname=copr_project,
                                                           packagename=copr_package)
        project_builds = [b for b in all_builds if b.state not in ('skipped', 'canceled')]
        if len(project_builds) == 0:
            log.debug('%s No previous builds found.', self._log_prefix)
            return None  # no previous builds, we are doing the first one

        last = max(project_builds, key=lambda x: x.submitted_on)

        log.debug('%s Found latest build: %s-%s (ID: %s)', self._log_prefix,
                  last.source_package['name'], last.source_package['version'], last.id)
        return last

    def _new_version(self, spec_version, copr_version, last_commit):
        '''Get new version based on current version in git and last build in Copr '''

        # build version might be another "version" and int('0.1') results in ValueError
        spec_build = int(spec_version.build.split('.')[0])

        if not copr_version:  # first build in copr
            release = str(spec_build + 1)
        elif LooseVersion(spec_version.version) > LooseVersion(copr_version.version):
            release = str(spec_build + 1)
        elif LooseVersion(spec_version.version) == LooseVersion(copr_version.version):
            release = str(int(copr_version.build) + 1)
        else:
            raise CoprBuilderError('Version from spec is older than last build in Copr')

        date = datetime.date.today().strftime('%Y%m%d')

        log.debug('%s New version: %s-%s.%sgit%s', self._log_prefix, spec_version.version, release, date, last_commit)

        return Version(spec_version.version, release, date, last_commit)
