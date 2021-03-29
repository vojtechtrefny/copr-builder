import datetime
import logging
import os
import time

import configparser
import copr

from copr.client_v2.common import BuildStateValues
from copr.client_v2.net_client import RequestError

from . import COPR_USER_CONF, COPR_REPO_CONF
from .errors import CoprBuilderError, CoprBuilderAlreadyFailed
from .copr_project import CoprProject


BUILD_URL_TEMPLATE = "%s/coprs/%s/%s/build/%s"
COPR_CONFIG = os.path.expanduser('~/.config/copr')


log = logging.getLogger("copr.builder")


class CoprBuilder(object):

    def __init__(self, conf_file, copr_config=None):

        self.config = configparser.ConfigParser()
        self.config.read(conf_file)

        self.copr_config = copr_config or COPR_CONFIG

        self._check_copr_token()
        self.copr = copr.create_client2_from_file_config(filepath=self.copr_config)

    def _check_copr_token(self):
        if not os.path.isfile(self.copr_config):
            raise CoprBuilderError('Copr configuration %s file not found.' % self.copr_config)

        expiration = None
        with open(self.copr_config, 'r') as f:
            for line in f:
                if line.startswith('# expiration date:'):
                    try:
                        expiration = datetime.datetime.strptime(line, "# expiration date: %Y-%m-%d\n")
                    except ValueError:
                        # parsing failed, just ignore it
                        pass

        if expiration is None:
            log.warning('Failed to get Copr token expiration date from config file.')
            return

        if expiration < datetime.datetime.now():
            raise CoprBuilderError('Your Copr token has expired. Expiration date: %s. '
                                   'Please obtain new and save it to %s.' % (expiration.strftime("%Y-%m-%d"),
                                                                             self.copr_config))

    def _check_projects_input(self, projects):
        wrong = [p for p in projects if p not in self.config.sections()]
        if wrong:
            raise CoprBuilderError('Requested project(s) %s not found in config.' % wrong)

    def do_builds(self, projects):
        srpms = {}
        success = True

        if projects:
            self._check_projects_input(projects)
        else:
            projects = self.config.sections()

        copr_projects = []

        # generate srpms for projects in config
        for project in projects:
            try:
                p = CoprProject(self.config[project], self.copr)
                # XXX: save reference to the CoprProject instance to avoid
                # automatic deletion of tempdir with the SRPM
                copr_projects.append(p)
                srpm = p.build_srpm()
                if srpm:
                    srpms[project] = srpm
            # previous build with the same srpm already failed, so do not try to
            # run the build again a just fail
            except CoprBuilderAlreadyFailed:
                success = False
            except CoprBuilderError as e:
                log.error('Failed to create SRPM for %s:\n%s', project, str(e))
                success = False

        # for all generated srpms run the copr build
        builds = []
        for project in srpms.keys():
            try:
                build = self._do_copr_build(project, srpms[project])
                builds.append(build)
            except CoprBuilderError as e:
                log.error('Failed to start Copr build for %s:\n%s', project, str(e))
                success = False

        # now remove the srpms, we no longer need them
        # some projects may actually share the same srpm, so it could be
        # already deleted
        for srpm in srpms.values():
            if os.path.exists(srpm):
                os.remove(srpm)

        return self._watch_builds(builds) and success

    def _get_copr_url(self, copr_user, copr_repo, build_id):
        if copr_user.startswith('@'):
            # for groups, the '@' symbol is replaced by 'g/'
            return BUILD_URL_TEMPLATE % (self.copr.root_url, 'g/' + copr_user[1:], copr_repo, build_id)
        else:
            return BUILD_URL_TEMPLATE % (self.copr.root_url, copr_user, copr_repo, build_id)

    def _do_copr_build(self, project, srpm):
        copr_user = self.config[project][COPR_USER_CONF]
        copr_repo = self.config[project][COPR_REPO_CONF]

        # get the project to extract project id
        plist = self.copr.projects.get_list(owner=copr_user, name=copr_repo)
        if len(plist.projects) != 1:
            raise CoprBuilderError('Expected to found exactly one Copr project for %s/%s but '
                                   'found %d' % (copr_user, copr_repo, len(plist.projects)))

        copr_project = plist.projects[0]

        try:
            build = copr_project.create_build_from_file(srpm)
        except RequestError as e:
            raise CoprBuilderError('Failed to create build') from e

        log.info('Started Copr build of %s (ID: %s)', srpm, build.id)
        log.info('Build URL: %s', self._get_copr_url(copr_user, copr_repo, build.id))

        return build

    def _print_chroot_states(self, build):
        tasks = build.get_build_tasks()
        tasks = sorted(list(tasks), key=lambda x: x.chroot_name)
        for task in tasks:
            log.info('\tChroot %s finished: %s', task.chroot_name, task.state)

    def _watch_builds(self, builds):
        success = True

        while builds:
            for build in builds:
                b = build._handle.get_one(build.id)  # pylint: disable=protected-access
                if b.state in (BuildStateValues.SKIPPED, BuildStateValues.FAILED,
                               BuildStateValues.SUCCEEDED, BuildStateValues.CANCELED):
                    log.info('Build of %s-%s (ID: %s) finished: %s',
                             b.package_name, b.package_version, b.id, b.state)
                    if b.state == BuildStateValues.FAILED:
                        success = False
                        self._print_chroot_states(b)
                    builds.remove(build)

            time.sleep(0.5)

        return success
