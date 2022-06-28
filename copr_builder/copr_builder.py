import datetime
import logging
import os
import time

import configparser

from copr.v3 import Client, CoprNoResultException, CoprRequestException

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
        self.copr = Client.create_from_config_file(path=self.copr_config)

    def _check_copr_token(self):
        if not os.path.isfile(self.copr_config):
            raise CoprBuilderError('Copr configuration %s file not found.' % self.copr_config)

        expiration = None
        with open(self.copr_config, 'r', encoding='utf-8') as f:
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
        build_ids = []
        for project in srpms.keys():
            try:
                build_id = self._do_copr_build(project, srpms[project])
                build_ids.append(build_id)
            except CoprBuilderError as e:
                log.error('Failed to start Copr build for %s:\n%s', project, str(e))
                success = False

        # now remove the srpms, we no longer need them
        # some projects may actually share the same srpm, so it could be
        # already deleted
        for srpm in srpms.values():
            if os.path.exists(srpm):
                os.remove(srpm)

        return self._watch_builds(build_ids) and success

    def _get_copr_url(self, copr_user, copr_repo, build_id):
        if copr_user.startswith('@'):
            # for groups, the '@' symbol is replaced by 'g/'
            return BUILD_URL_TEMPLATE % (self.copr.config['copr_url'], 'g/' + copr_user[1:], copr_repo, build_id)
        else:
            return BUILD_URL_TEMPLATE % (self.copr.config['copr_url'], copr_user, copr_repo, build_id)

    def _do_copr_build(self, project, srpm):
        copr_user = self.config[project][COPR_USER_CONF]
        copr_repo = self.config[project][COPR_REPO_CONF]

        # get the project to extract project id
        try:
            self.copr.project_proxy.get(ownername=copr_user, projectname=copr_repo)
        except CoprNoResultException as e:
            raise CoprBuilderError('Copr project %s/%s not found' % (copr_user, copr_repo)) from e

        try:
            build = self.copr.build_proxy.create_from_file(ownername=copr_user,
                                                           projectname=copr_repo,
                                                           path=srpm)
        except CoprRequestException as e:
            raise CoprBuilderError('Failed to create build') from e

        # pylint: disable=no-member
        log.info('Started Copr build of %s (ID: %s)', srpm, build.id)
        log.info('Build URL: %s', self._get_copr_url(copr_user, copr_repo, build.id))

        return build.id

    def _print_chroot_states(self, build):
        # pylint: disable=no-member
        chroots = sorted(build.chroots)
        for chroot in chroots:
            task = self.copr.build_chroot_proxy.get(build_id=build.id, chrootname=chroot)
            log.info('\tChroot %s finished: %s', task.name, task.state)

    def _watch_builds(self, build_ids):
        success = True

        # pylint: disable=no-member
        while build_ids:
            for build_id in build_ids:
                build = self.copr.build_proxy.get(build_id)
                if build.state in ('skipped', 'failed', 'succeeded', 'canceled'):
                    log.info('Build of %s-%s (ID: %s) finished: %s',
                             build.source_package['name'], build.source_package['version'],
                             build.id, build.state)
                    if build.state == 'failed':
                        success = False
                        self._print_chroot_states(build)
                    build_ids.remove(build_id)

            time.sleep(0.5)

        return success
