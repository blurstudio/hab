import os
import string

from . import utils


class Formatter(string.Formatter):
    """A extended string formatter class to parse habitat configurations.

    Adds support for the "!e" conversion flag. This will fill in the key as a properly
    formatted environment variable specifier. For example ''{PATH!e}'' will be converted
    to ``$PATH`` for the sh language, and ``%env:PATH`` for the ps language. You can
    convert "!e" to "!s" by setting expand to True. This simulates `os.path.expandvars`.

    This also converts ``{;}`` to the language specific path separator for environment
    variables. On linux this is ``:`` on windows(even in bash) this is ``;``.

    You need to specify the desired language when initializing this class. This can be
    one of the supported language keys in ''Formatter.shell_formats'', or you can pass
    a file extension supported by `Formatter.language_from_ext`. If you pass None, it
    will preserve the formatting markers so it can be converted later.
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

    def __init__(self, language, expand=False):
        super().__init__()
        self.language = self.language_from_ext(language)
        self.current_field_name = None
        self.expand = expand

    def convert_field(self, value, conversion):
        if conversion == "e":
            # Expand the env var to the real string value simulating `os.path.expandvars`
            if self.expand:
                return super().convert_field(value, "s")

            # Otherwise insert the correct shell script env var reference
            return self.shell_formats[self.language]["env_var"].format(
                self.current_field_name
            )

        return super().convert_field(value, conversion)

    def get_field(self, field_name, args, kwargs):
        self.current_field_name = field_name
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

    def merge_kwargs(self, kwargs):
        """Merge the provided kwargs on top of the current language's shell_formats
        dict. This makes it so the default format options are added by default, but
        still allows us to override them if required
        """
        ret = dict(self.shell_formats[self.language], **kwargs)
        ret = dict(os.environ, **ret)
        return ret

    def vformat(self, format_string, args, kwargs):
        kwargs = self.merge_kwargs(kwargs)
        ret = super().vformat(format_string, args, kwargs)
        return ret
