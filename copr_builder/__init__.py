from collections import namedtuple

PACKAGE_CONF = 'package'
COPR_USER_CONF = 'copr_user'
COPR_REPO_CONF = 'copr_repo'
GIT_URL_CONF = 'git_url'
GIT_BRANCH_CONF = 'git_branch'
GIT_MERGE_BRANCH_CONF = 'git_merge_branch'
ARCHIVE_CMD_CONF = 'archive_cmd'


Version = namedtuple('Version', ['version', 'build', 'date', 'git_hash'])
