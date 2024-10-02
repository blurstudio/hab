import os
import string

from . import utils


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
        expand(bool, optional): Should the ``!e`` conversion insert the shell
            environment variable specifier or the value of the env var?

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

    def __init__(self, language, expand=False):
        super().__init__()
        self.language = self.language_from_ext(language)
        self.expand = expand

    def get_field(self, field_name, args, kwargs):
        """Returns the object to be inserted for the given field_name.

        If kwargs doesn't contain ``field_name`` but ``field_name`` is in the
        environment variables, the stored value is returned. This also returns
        the pathsep for the ``;`` field_name. Otherwise works the same as
        the standard `string.Formatter`_.

        .. _`string.Formatter`:
           https://docs.python.org/3/library/string.html#string.Formatter.get_field
        """
        # If a field_name was not provided, use the value stored in os.environ
        if field_name not in kwargs and field_name in os.environ:
            return os.getenv(field_name), field_name
        # Process the pathsep character
        if field_name == ";":
            value = self.shell_formats[self.language][";"]
            return value, field_name

        ret = super().get_field(field_name, args, kwargs)
        return ret

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
            # Non-hab specific operation, just use the super value unchanged
            if conversion != "e":
                yield (literal_text, field_name, format_spec, conversion)
                continue

            elif self.expand and field_name in os.environ:
                # Expand the env var to the env var value. Later `get_field`
                # will update kwargs with the existing env var value
                yield (literal_text, field_name, format_spec, "s")
                continue

            # Convert this !e conversion to the shell specific env var specifier
            value = self.shell_formats[self.language]["env_var"].format(field_name)
            yield (literal_text + value, None, None, None)
