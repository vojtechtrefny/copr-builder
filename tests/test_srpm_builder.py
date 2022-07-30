import pytest
import os
import shutil

from copr_builder import GIT_URL_CONF, PACKAGE_CONF, ARCHIVE_CMD_CONF, GIT_BRANCH_CONF
from copr_builder.srpm_builder import SRPMBuilder


def test_build_srpm():
    if not shutil.which("rpmbuild"):
        pytest.skip("rpmbuild not available")

    # try to build copr-builder srpm from git
    project_data = {GIT_URL_CONF: "https://github.com/vojtechtrefny/copr-builder",
                    PACKAGE_CONF: "copr-builder",
                    ARCHIVE_CMD_CONF: "make local",
                    GIT_BRANCH_CONF: "master"}

    srpm_builder = SRPMBuilder(project_data)
    srpm_builder.prepare_build()
    srpm_builder.make_archive()
    srpm = srpm_builder.build()

    assert srpm is not None
    assert os.path.exists(srpm)

    srpm_name = os.path.basename(srpm)
    assert srpm_name.startswith("copr-builder")
    assert srpm_name.endswith("src.rpm")
