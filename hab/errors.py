class HabError(Exception):
    """Base class for all hab errors."""


class DuplicateJsonError(HabError):
    """Raised if the same context/name is re-defined inside a single config/distro
    path definition. This is allowed for unique `Resolver.config_paths` and the first
    path that defines it is the one used, but if the same context is used inside a
    single path this error is raised.
    """


class RequirementError(HabError):
    """Base class for Requirement parsing errors."""


class _IgnoredVersionError(RequirementError):
    """Internal exception raised if a distro version is ignored."""


class MaxRedirectError(RequirementError):
    """The maximum number of redirects was reached without resolving successfully."""


class InvalidRequirementError(RequirementError):
    """Raised if unable to resolve a given requirement."""


class InvalidVersionError(LookupError):
    """Provides info on resolving why it was unable to generate a valid version number"""

    default_message = (
        'Hab was unable to determine the version for "{filename}".\n'
        "  The version is defined in one of several ways checked in this order:\n"
        "  1. The version property in `.hab.json`.\n"
        "  2. A `.hab_version.txt` file next to `.hab.json`.\n"
        "  3. `.hab.json`'s parent directory name.\n"
        "  4. setuptools_scm can get a version from version control.\n"
        "  The preferred method is #3 for deployed releases. #4 is the "
        "preferred method for developer working copies."
    )

    def __init__(self, filename, error=None, message=None):
        self.filename = filename
        self.error = error
        if message is None:
            message = self.default_message
        self.message = message

    def __str__(self):
        ret = self.message.format(filename=self.filename)
        if self.error:
            ret = f"[{type(self.error).__name__}] {self.error}\n{ret}"
        return ret
