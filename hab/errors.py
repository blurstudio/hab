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


class InvalidAliasError(HabError):
    """Raised the requested alias was not found.

    Args:
        alias (str): The requested alias name.
        cfg (hab.parser.Config): The hab config used to launch the alias.
        msg (str, optional): The error message. `str.format` is called on this
            passing the kwargs `alias` and `uri`.
    """

    def __init__(self, alias, cfg, msg=None):
        self.alias = alias
        self.cfg = cfg
        if msg is None:
            msg = 'The alias "{alias}" is not found for URI "{uri}".'
        super().__init__(msg.format(alias=alias, uri=cfg.uri))


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


class ReservedVariableNameError(HabError):
    """Raised if a custom variable uses a reserved variable name."""

    _reserved_variable_names = {"relative_root", ";"}
    """A set of variable names hab reserved for hab use and should not be defined
    by custom variables."""

    def __init__(self, invalid, filename):
        self.filename = filename
        msg = (
            f"{', '.join(sorted(invalid))!r} are reserved variable name(s) for "
            "hab and can not be used in the variables section. "
            f"Filename: '{self.filename}'"
        )
        super().__init__(msg)
