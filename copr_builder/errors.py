
class CoprBuilderError(Exception):
    pass


class GitError(CoprBuilderError):
    pass


class SRPMBuilderError(CoprBuilderError):
    pass


class CoprBuilderAlreadyFailed(CoprBuilderError):
    pass


class CoprBuilderConfigurationError(CoprBuilderError):
    pass


class CoprBuilderBrokenGitHash(CoprBuilderError):
    pass
