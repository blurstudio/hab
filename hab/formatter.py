import enum
import logging
import os
import string
from contextlib import contextmanager

from . import utils

logger = logging.getLogger(__name__)


class ExpandMode(enum.Enum):
    """Defines how Formatter handles the habitat-specific ``!e`` conversion field."""

    Preserve = (1, False)
    """Preserve the conversion marker.
    This returns the environment variable specifier or the original marker.
    ('-{A!e}-' -> `-{A!e}-` or ``-$A-`` depending on the target shell)."""

    ToShell = (2, True)
    """Convert to the shell's environment variable.
    Returns a shell-specific environment variable reference.
    ('-{A!e}-' -> `-$A-` or ``-%env:A-``)."""

    Remove = (3, True)
    """Replace with an empty string.
    ('-{A!e}-' -> `--`)."""

    def __init__(self, value, expand) -> None:
        self._value_ = value
        self.expand = expand

    def __str__(self):
        return self.name


@contextmanager
def format_feedback(value, key=None, parser=None, platform=None):
    try:
        yield
    except KeyError as error:
        data = {}
        if key:
            data["key"] = key
        data["value"] = value
        if platform:
            data["platform"] = platform
        if parser:
            if parser.filename:
                data["filename"] = parser.filename.as_posix()
            else:
                data["parser"] = parser
        raise KeyError(f"Error formatting: {data}") from error


class Formatter(string.Formatter):
    """A extended string formatter class to parse habitat configurations.

    Adds support for the ``!e`` `conversion field`_. This will fill in the key as a
    properly formatted environment variable specifier. For example ``{PATH!e}`` will
    be converted to ``$PATH`` for the sh language, and ``%env:PATH`` for the ps language.

    By setting expand to True the ``!e`` conversion field will be filled in with the
    environment variable for that key if the env variable is set. Otherwise it will
    fall back the environment variable specifier.

    This also converts ``{;}`` to the language specific path separator for environment
    variables. On linux this is ``:`` on windows(even in bash) this is ``;``.

    Parameters:
        language: Specify the shell language to use when converting ``!e``. See
            :py:const:`Formatter.shell_formats` and :py:meth:`Formatter.language_from_ext`.
            for supported values. If you pass None, it will preserve the
            formatting markers so it can be converted later.
        expand(ExpandMode, optional): Controls how the ``!e`` conversion is handled.

    .. _conversion field:
       https://docs.python.org/3/library/string.html#grammar-token-format-string-conversion
    """

    shell_formats = {
        # Command Prompt
        "batch": {
            "env_var": "%{}%",
            ";": ";",
        },
        # Power Shell
        "ps": {
            "env_var": "$env:{}",
            ";": ";",
        },
        # Using bash on linux
        "sh": {
            "env_var": "${}",
            ";": ":",
        },
        # Using bash on windows
        "shwin": {
            "env_var": "${}",
            ";": ":",
        },
        # Delay the format for future calls. This allows us to process the environment
        # without changing these, and then when write_script is called the target
        # scripting language is resolved.
        None: {
            "env_var": "{{{}!e}}",
            ";": "{;}",
        },
    }
    """Information on how to generate shell specific environment variable references
    and the character to use for pathsep. For each shell ``env_var`` is a format
    string that accepts the env var name. ``;`` is the path separator to use.
    """

    def __init__(self, language, expand=ExpandMode.Preserve):
        super().__init__()
        self.language = self.language_from_ext(language)
        self.expand = expand

    def get_field(self, field_name, args, kwargs):
        """Returns the value for the given field_name.

        This method extends the standard `string.Formatter.get_field` to handle:

        1. **Path Separators**: If ``field_name`` is ``;``, returns the language-specific
           path separator (e.g., ``:`` for sh, ``;`` for batch/ps).
        2. **Automatic List Joining**: If the value in ``kwargs`` is a list, it is
           automatically joined using the language-specific path separator.
        3. **Environment Expansion (!e only)**: If the field uses the ``!e`` conversion,
           exists in ``os.environ``, and expansion is enabled (via :py:const:`ExpandMode`),
           the environment value is returned. Standard fields (``!s``) do not trigger
           environment expansion.
        4. **Fallback Handling (!e only)**: If an ``!e`` field is missing from both
           ``kwargs`` and the environment, the behavior is determined by the
           :py:attr:`expand` mode. See :py:class:`ExpandMode` for details. Standard
           fields (``!s``) use the default `string.Formatter` fallback behavior.

        Otherwise, it falls back to the standard `string.Formatter`_ implementation.
        !e mode is enabled if field_name ends with :e.

        .. _`string.Formatter`:
           https://docs.python.org/3/library/string.html#string.Formatter.get_field
        """
        do_expand = False
        if field_name.endswith(":e"):
            field_name = field_name[:-2]
            do_expand = True

        # Process the pathsep character
        if field_name == ";":
            value = self.shell_formats[self.language][";"]
            return value, field_name

        if field_name in kwargs:
            value = kwargs[field_name]
            # If the value is a list, join it using the language specific pathsep
            if isinstance(value, list):
                pathsep = self.shell_formats[self.language][";"]
                value = pathsep.join([str(v) for v in value])
            return value, field_name

        # If a field_name was not provided, use the value stored in os.environ
        # Only if the mode allows expansion and !e was used.
        if do_expand and self.expand.expand and field_name in os.environ:
            return os.getenv(field_name), field_name

        # Default fallback logic for !e markers (parse forces to conversion='s')
        if do_expand:
            if self.expand == ExpandMode.ToShell:
                return (
                    self.shell_formats[self.language]["env_var"].format(field_name),
                    field_name,
                )
            elif self.expand == ExpandMode.Remove:
                return "", field_name
            elif self.expand == ExpandMode.Preserve:
                # Preserve mode returns the shell specifier or marker
                lang_formats = self.shell_formats[self.language]
                return lang_formats["env_var"].format(field_name), field_name

        return super().get_field(field_name, args, kwargs)

    @classmethod
    def language_from_ext(cls, ext):
        """Turn the provided file ext into the common name for that language.
        This can be used to find the correct data for the cls.shell_formats mapping.

        ".bat" and ".cmd" return "batch". ".ps1" returns "ps". ".sh" or an empty
        string return "sh" if on linux and "shwin" if on windows. If `None` is passed
        the format will be replaced with the same format command so future format
        calls can re-apply the changes. Any other value passed is returned unmodified.
        """
        if ext in (".bat", ".cmd"):
            return "batch"
        elif ext == ".ps1":
            return "ps"
        elif ext in (".sh", ""):
            # Assume no ext is a .sh file
            if utils.Platform.name() == "windows":
                return "shwin"
            else:
                return "sh"
        return ext

    def parse(self, txt):
        for literal_text, field_name, format_spec, conversion in super().parse(txt):
            if conversion == "e":
                # If the conversion is !e, encode that into the field_name so
                # later get_field can enable the extra features it provides, but
                # !s does not get those special features enabled.
                yield (literal_text, f"{field_name}:e", format_spec, "s")
                continue

            yield (literal_text, field_name, format_spec, conversion)
