class RequirementError(Exception):
    """Base class for Requirement parsing errors."""


class MaxRedirectError(RequirementError):
    """The maximum number of redirects was reached without resolving successfully."""
