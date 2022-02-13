import pytest
import tempfile
from contextlib import contextmanager
from datetime import date

from copr.v3 import Client

from copr_builder.copr_builder import CoprBuilder
from copr_builder.errors import CoprBuilderError

from utils import write_file

COPR_FILE = """[copr-cli]
login = aaaaaaaaaaaaa
username = aaaaaa
token = aaaaaaaaaaaaaaaaaaa
copr_url = https://copr.fedorainfracloud.org
# expiration date: {date}
"""

BUILDER_FILE = """[projectA]
copr_user = userA
copr_repo = repoA
package = packageA
git_url = urlA
archive_cmd = cmdA
git_branch = branchA

[projectB]
copr_user = userB
copr_repo = repoB
package = packageB
git_url = urlB
archive_cmd = cmdB
git_branch = branchB
"""


@contextmanager
def prepare_config_files():
    copr_file = tempfile.NamedTemporaryFile()
    builder_file = tempfile.NamedTemporaryFile()

    yield (copr_file.name, builder_file.name)

    copr_file.close()
    builder_file.close()


def test_token_checking(monkeypatch):
    monkeypatch.setattr(Client, "create_from_config_file", lambda path: None)

    today = date.today()

    # token expired one year ago -- should fail
    with prepare_config_files() as (builder_file, copr_file):
        write_file(copr_file, COPR_FILE.format(date=today.replace(year=today.year - 1)))

        with pytest.raises(CoprBuilderError):
            CoprBuilder(builder_file, copr_file)

        # token will expire in one year -- should pass
        write_file(copr_file, COPR_FILE.format(date=today.replace(year=today.year + 1)))

        CoprBuilder(builder_file, copr_file)


def test_config_parsing(monkeypatch):
    monkeypatch.setattr(Client, "create_from_config_file", lambda path: None)
    today = date.today()

    with prepare_config_files() as (builder_file, copr_file):
        write_file(builder_file, BUILDER_FILE)
        write_file(copr_file, COPR_FILE.format(date=today.replace(year=today.year + 1)))

        builder = CoprBuilder(builder_file, copr_file)

        # there should be 2 projects parsed from the config -- projectA and projectB
        builder._check_projects_input(["projectA", "projectB"])
        with pytest.raises(CoprBuilderError):
            builder._check_projects_input(["projectC"])

        for project in ("A", "B"):
            assert builder.config["project" + project]["copr_user"] == "user" + project
            assert builder.config["project" + project]["copr_repo"] == "repo" + project
            assert builder.config["project" + project]["package"] == "package" + project
            assert builder.config["project" + project]["git_url"] == "url" + project
            assert builder.config["project" + project]["archive_cmd"] == "cmd" + project
            assert builder.config["project" + project]["git_branch"] == "branch" + project
