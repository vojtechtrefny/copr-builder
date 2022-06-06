#!/usr/bin/python3

import sys

from pocketlint import PocketLintConfig, PocketLinter, FalsePositive


class CoprBuilderSetupLintConfig(PocketLintConfig):
    def __init__(self):
        PocketLintConfig.__init__(self)

        self.falsePositives = [FalsePositive(r"test_.*: Access to a protected member"),
                               FalsePositive(r"Instance of 'List' has no '(id|state|name|source_package)' member")]

    @property
    def pylintPlugins(self):
        retval = super(CoprBuilderSetupLintConfig, self).pylintPlugins
        return retval

    @property
    def disabledOptions(self):
        return ["W0511",           # Used when a warning note as FIXME or XXX is detected.
                "I0011",           # Locally disabling %s
                ]


if __name__ == "__main__":
    conf = CoprBuilderSetupLintConfig()
    linter = PocketLinter(conf)
    rc = linter.run()
    sys.exit(rc)
