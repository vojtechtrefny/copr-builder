import pytest
import tempfile
from contextlib import contextmanager
from datetime import date

from copr.v3 import Client

from copr_builder import CoprBuilderVersion
from copr_builder.copr_builder import CoprBuilder
from copr_builder.copr_project import CoprProject
from copr_builder.errors import CoprBuilderError
from copr_builder.git_repo import GitRepo

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


class MockCoprClient:
    @property
    def project_proxy(self):
        return self

    def get(self, ownername, projectname):
        pass


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


def test_version(monkeypatch):
    monkeypatch.setattr(Client, "create_from_config_file", lambda path: MockCoprClient())
    monkeypatch.setattr(GitRepo, "clone", lambda _: None)

    with prepare_config_files() as (builder_file, copr_file):
        today = date.today()
        write_file(builder_file, BUILDER_FILE)
        write_file(copr_file, COPR_FILE.format(date=today.replace(year=today.year + 1)))

        builder = CoprBuilder(builder_file, copr_file)

        cp = CoprProject(builder.config["projectA"], builder.copr)
        ver = cp._extract_version("2.33-8.20170322gitcb678c83.fc26")

        assert ver.version == "2.33"
        assert ver.build == "8"
        assert ver.date == "20170322"
        assert ver.git_hash == "cb678c83"

        # no last build in copr
        commit = "eb925dd6"
        spec_ver = CoprBuilderVersion(version="2.33", build="1", date=None, git_hash=None)
        new_ver = cp._new_version(spec_ver, None, commit)
        assert new_ver.version == spec_ver.version
        assert new_ver.build == str(int(spec_ver.build) + 1)
        assert new_ver.date == date.today().strftime('%Y%m%d')
        assert new_ver.git_hash == commit

        # last build in coper is older
        copr_ver = CoprBuilderVersion(version="2.32", build="2", date="20170322", git_hash="cb678c83")
        new_ver = cp._new_version(spec_ver, copr_ver, commit)
        assert new_ver.version == spec_ver.version
        assert new_ver.build == str(int(spec_ver.build) + 1)
        assert new_ver.date == date.today().strftime('%Y%m%d')
        assert new_ver.git_hash == commit

        # last build in coper is the same
        copr_ver = CoprBuilderVersion(version="2.33", build="5", date="20170322", git_hash="cb678c83")
        new_ver = cp._new_version(spec_ver, copr_ver, commit)
        assert new_ver.version == spec_ver.version
        assert new_ver.build == str(int(copr_ver.build) + 1)
        assert new_ver.date == date.today().strftime('%Y%m%d')
        assert new_ver.git_hash == commit
