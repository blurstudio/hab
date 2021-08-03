class RequirementError(Exception):
    """Base class for Requirement parsing errors."""


class DistroNotDefined(RequirementError):
    """No distro was found that matches the given requirements."""


class MaxRedirectError(RequirementError):
    """The maximum number of redirects was reached without resolving successfully."""


class NoValidVersion(RequirementError):
    """Unable to find a valid version from the requested requirement."""
