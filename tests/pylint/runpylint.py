#!/usr/bin/python3

import sys

from pocketlint import PocketLintConfig, PocketLinter, FalsePositive


class CoprBuilderSetupLintConfig(PocketLintConfig):
    def __init__(self):
        PocketLintConfig.__init__(self)

        # both happens only in travis, see https://github.com/PyCQA/pylint/issues/73
        self.falsePositives = [FalsePositive(r"No name '(core|version)' in module 'distutils'"),
                               FalsePositive(r"Unable to import 'distutils\.(core|version)'"),
                               FalsePositive(r"test_.*: Access to a protected member"),
                               FalsePositive(r"Instance of 'List' has no '(id|state|name|source_package)' member")]

    @property
    def pylintPlugins(self):
        retval = super(CoprBuilderSetupLintConfig, self).pylintPlugins
        return retval

    @property
    def disabledOptions(self):
        return ["W0142",           # Used * or ** magic
                "W0511",           # Used when a warning note as FIXME or XXX is detected.
                "I0011",           # Locally disabling %s
                ]


if __name__ == "__main__":
    conf = CoprBuilderSetupLintConfig()
    linter = PocketLinter(conf)
    rc = linter.run()
    sys.exit(rc)
