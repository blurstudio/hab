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
