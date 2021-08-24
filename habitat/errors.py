class HabitatError(Exception):
    """Base class for all habitat errors."""


class DuplicateJsonError(HabitatError):
    """Raised if the same context/name is re-defined inside a single config/distro
    path definition. This is allowed for unique `Resolver.config_paths` and the first
    path that defines it is the one used, but if the same context is used inside a
    single path this error is raised.
    """


class RequirementError(HabitatError):
    """Base class for Requirement parsing errors."""


class MaxRedirectError(RequirementError):
    """The maximum number of redirects was reached without resolving successfully."""
