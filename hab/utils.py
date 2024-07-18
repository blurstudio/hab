import base64
import errno
import json as _json
import logging.config
import ntpath
import os
import re
import sys
import textwrap
import zlib
from abc import ABC, abstractmethod
from collections import UserDict
from collections.abc import KeysView
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path, PurePath

import colorama

# Attempt to use pyjson5 if its installed, this allows us to add comments
# to the various json documents, but is not required. Trailing comments FTW!
try:
    import pyjson5 as json
    from pyjson5 import Json5Exception as _JsonException
except ImportError:
    import json

    class _JsonException(BaseException):
        """Placeholder exception when pyjson5 is not used. Should never be raised"""


colorama.init()

re_windows_single_path = re.compile(r"^([a-zA-Z]:[\\\/][^:;]+)$")
"""A regex that can be used to check if a string is a single windows file path."""


def cygpath(path, spaces=False):
    """Convert a windows path to a cygwin compatible path. For example `c:\\test`
    converts to `/c/test`. This also works for unc file paths.

    Note: This doesn't use cygpath.exe for greater portability. Ie its accessible
    even if the current shell doesn't have access to cygpath.exe. It also doesn't
    require extra suprocess calls.

    Args:
        path (str): The file path to convert.
        spaces (bool, optional): Add a backslash before every non-escaped space.
    """
    path = str(path)

    # Escape spaces and convert any remaining backslashes to forward slashes
    def process_separator(match):
        sep = path[match.start() : match.end()]
        slash_count = sep.count("\\")
        if " " not in sep:
            # It's not a space, simply replace with forward-slash
            return sep.replace("\\", "/")
        # Treat odd numbers of slashes as already escaped not directories.
        elif not spaces or slash_count % 2:
            return sep
        # Add a backslash to escape spaces if enabled
        return sep.replace(" ", "\\ ")

    pattern = (
        # Capture spaces including any leading backslashes to escape
        r"(\\* )"
        # If we can't find any spaces, capture backslashes to convert to forward-slash
        r"|(\\+)"
    )
    path = re.sub(pattern, process_separator, path)

    # Finally, convert `C:\` drive specifier to `/c/`. Unc paths don't need any
    # additional processing, just converting \ to / which was done previously.
    drive, tail = ntpath.splitdrive(path)
    if len(drive) == 2 and drive[1] == ":":
        # It's a drive letter
        path = f"/{drive[0]}{tail}"
    return path


def decode_freeze(txt):
    """Decodes the provided frozen hab string. See `encode_freeze` for
    details on how these strings are encoded. These will start with a version
    identifier `vX:` where X denotes the version it was encoded with."""

    # Extract version information from the string
    try:
        version, txt = txt.split(":", 1)
        if version[0] != "v":
            raise ValueError("Missing v prefix in version information.")
    except ValueError:
        raise ValueError(
            "Missing freeze version information in format `v0:...`"
        ) from None
    try:
        version = int(version[1:])
    except ValueError:
        raise ValueError(f"Version {version[1:]} is not valid.") from None

    data = txt.encode("ascii")
    data = base64.b64decode(txt)
    if version == 1:
        data = data.decode("utf-8")
    elif version == 2:
        data = zlib.decompress(data).decode()
    else:
        return None
    return json.loads(data)


def dump_object(obj, label="", width=80, flat_list=False, color=False):
    """Recursively convert python objects into a human readable table string.

    Args:
        obj: The object to convert. This is called recursively for dicts and
            lists, other objects are simply cast as a string.
        label (str, optional): Prefix the first line with this text, and any
            additional lines are prefixed with white space of the same length.
            Include any desired formatting including white space.
        width (int, optional): The desired width for wrapping. The output may
            exceed this value, but it will attempt to respect it.
        flat_list (bool, optional): By default for lists, it will attempt to
            store multiple list items on a single line, but if that ends up
            exceeding width, it will switch to a line per item, this is useful
            for path output. Setting this to True will force it to put as many
            items on a single line as possible instead. It will not allow an
            item to be broken into multiple lines.
        color (bool, optional): Use ANSI escape character sequences to colorize
            the output of the text.
    """
    pad = " " * len(label)
    if label:
        width = width - len(label)
        if width < 10:
            width = 10
        if color:
            label = f"{colorama.Fore.GREEN}{label}{colorama.Style.RESET_ALL}"

    if isinstance(obj, (list, KeysView)):
        rows = []
        obj = [
            dump_object(o, width=width, flat_list=flat_list, color=color) for o in obj
        ]
        if flat_list:
            # combine as many list items as possible onto each line
            # Use non-breaking spaces to prevent word wrap for each item.
            obj = textwrap.wrap(
                " ".join([x.replace(" ", "u\00A0") for x in obj]),
                width=width,
                break_long_words=False,
            )
            # Remove those pesky non-breaking spaces
            obj = [x.replace("u\00A0", " ") for x in obj]
            one_row = ", ".join(obj)
            multi_row = len(obj) > 1
        else:
            # Determine if we can store all of this on a single line within
            # the requested width
            one_row = ", ".join(obj)
            multi_row = len(one_row) > width

        if multi_row:
            rows.append(f"{label}{obj[0]}")
            rows.extend([f"{pad}{o}" for o in obj[1:]])
        else:
            rows = [f"{label}{one_row}"]

        return "\n".join(rows)
    elif isinstance(obj, (dict, UserDict)):
        rows = []
        lbl = label
        for k, v in sorted(obj.items()):
            rows.append(
                dump_object(
                    v,
                    label=f"{lbl}{k}:  ",
                    width=width,
                    flat_list=flat_list,
                    color=color,
                )
            )
            lbl = pad
        return "\n".join(rows)
    elif isinstance(obj, PurePath):
        return f"{label}{obj}"
    elif hasattr(obj, "name"):
        # Likely HabBase objects
        return f"{label}{obj.name}"
    # Simply convert any other objects to strings
    return f"{label}{obj}"


def dump_title(title, body, color=False):
    """Returns the body with title and wrapped in a header and footer line

    Args:
        title (str): The title to add before the header line.
        body (str): The text to be wrapped in the header and footer lines.
        color (bool, optional): Use ANSI escape character sequences to colorize
            the output of the text.
    """
    # Find the max width of the body and title to add the line
    width = len(max(body.split("\n"), key=len))
    width = max(len(title), width)
    if color:
        title = f"{colorama.Fore.GREEN}{title}{colorama.Style.RESET_ALL}"
    return f"{title}\n{'-'*width}\n{body}\n{'-'*width}"


def dumps_json(data, **kwargs):
    """Consistent method for calling json.dumps that handles encoding custom
    data objects like NotSet.

    Pyjson5's dump is not as fully featured as python's json, so this ensures
    consistent dumps output as python's json module has more features than
    pyjson5. For example pyjson5 doesn't support indent."""
    kwargs.setdefault("cls", HabJsonEncoder)
    return _json.dumps(data, **kwargs)


def encode_freeze(data, version=None, site=None):
    """Encodes the provided data object in json. This string is stored on the
    "HAB_FREEZE" environment variable when run by the cli.

    Encoded freeze version data is a string with a version prefix matching the
    regex `v(?P<ver>\\d+):(?P<freeze>.+)`.

    Version 1: Encodes data to a json string that is then encoded with base64.
    Version 2: Encodes data to a json string that is then compressed with zlib,
        and finally encoded with base64.
    None is returned if this version number is not supported.

    Args:
        data: The data to freeze.
        version (int, optional): The version to encode the freeze with.
            If None is passed, then the default version encoding is used.
        site (hab.site.Site, optional): If version is not specified, then
            attempt to get version from `site.get("freeze_version")`.
    """
    if version is None and site:
        version = site.get("freeze_version")

    if version is None:
        # The current default is 2. Using None makes it easy to control this
        # with a site configuration.
        version = 2

    data = dumps_json(data)
    data = data.encode("utf-8")
    if version == 1:
        data = base64.b64encode(data)
    elif version == 2:
        data = zlib.compress(data)
        data = base64.b64encode(data)
    else:
        return None

    return f'v{version}:{data.decode("utf-8")}'


class HabJsonEncoder(_json.JSONEncoder):
    """JsonEncoder class that handles non-supported objects like hab.NotSet."""

    def default(self, obj):
        if obj is NotSet:
            # Convert NotSet to None for json storage
            return None
        # Handle date and datetime conversion
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()

        # Let the base class default method raise the TypeError
        return _json.JSONEncoder.default(self, obj)


def load_json_file(filename):
    """Open and parse a json file. If a parsing error happens the file path is
    added to the exception to allow for easier debugging.

    Args:
        filename (pathlib.Path): A existing file path.

    Returns:
        The data stored in the json file.

    Raises:
        FileNotFoundError: If filename is not pointing to a file that actually exists.
        pyjson5.Json5Exception: If using pyjson5, the error raised due to invalid json.
        ValueError: If not using pyjson5, the error raised due to invalid json.
    """
    if not filename.is_file():
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), str(filename))

    with filename.open() as fle:
        try:
            data = json.load(fle)
        # Include the filename in the traceback to make debugging easier
        except _JsonException as e:
            # pyjson5 is installed add filename to the traceback
            if e.result is None:
                # Depending on the exception result may be None, convert it
                # into a empty dict so we can add the filename
                e.args = e.args[:1] + ({},) + e.args[2:]
            e.result["filename"] = str(filename)
            raise e.with_traceback(sys.exc_info()[2]) from None
        except ValueError as e:
            # Using python's native json parser
            msg = f'{e} Filename("{filename}")'
            raise type(e)(msg, e.doc, e.pos).with_traceback(sys.exc_info()[2]) from None
    return data


def natural_sort(ls, key=None):
    """Sort a list in a more natural way by treating contiguous integers as a
    single number instead of processing each number individually. This function
    understands that 10 is larger than 1. It also ignores case.

    Source: http://blog.codinghorror.com/sorting-for-humans-natural-sort-order
    """

    def convert(text):
        return int(text) if text.isdigit() else text.lower()

    if key is None:

        def key(text):
            return text

    def alphanum_key(a_key):
        return [convert(c) for c in re.split(r"([0-9]+)", key(a_key))]

    return sorted(ls, key=alphanum_key)


class NotSet(object):
    """The data for this property is not currently set."""

    def __bool__(self):
        """NotSet should be treated as False when booled Python 3"""
        return False

    def __str__(self):
        return "NotSet"

    def __copy__(self):
        """Does not return a copy of this object, NotSet is intended to be a
        singleton so it does not copy itself."""
        return self

    def __deepcopy__(self, memo):
        """Does not return a copy of this object, NotSet is intended to be a
        singleton so it does not copy itself."""
        return self

    def __reduce__(self):
        """Enable pickling of NotSet."""
        return type(self).__qualname__


# Make this a singleton so it works like a boolean False for if statements.
NotSet = NotSet()


def path_forward_slash(path):
    """Converts a Path object into a string with forward slashes"""
    return str(path).replace("\\", "/")


@contextmanager
def verbosity_filter(resolver, verbosity, target=None):
    """Change the verbosity settings of a hab.Resolver while inside this with
    context.

    Args:
        resolver (hab.Resolver): The resolver to change verbosity settings on.
        verbosity (int): Change the verbosity setting to this value. If None is
            passed, all results are be shown without any filtering.
        target (str, optional): Change the verbosity target, ignored if None.
    """
    # Backup the current values
    current_target = resolver._verbosity_target
    current_value = resolver._verbosity_value

    # Change to the requested values
    if target is not None:
        resolver._verbosity_target = target
    resolver._verbosity_value = verbosity

    try:
        yield
    finally:
        # Restore the original values
        resolver._verbosity_target = current_target
        resolver._verbosity_value = current_value


class BasePlatform(ABC):
    """Subclasses of BasePlatform are the interface hab uses to handle cross
    platform code.

    The current platform is accessible via hab.utils.Platform which is set by
    calling `BasePlatform.get_platform()`. To change the current platform, set
    the subclass to Platform. `hab.utils.Platform = hab.utils.WinPlatform`
    """

    _default_ext = ".sh"
    _name = None
    _sep = ":"

    @classmethod
    def configure_logging(cls, filename=None):
        """Update the logging configuration with the contents of this json file
        if exists.

        See https://docs.python.org/3/library/logging.config.html#dictionary-schema-details
        for details on how to construct this file.

        You will most likely want to enable incremental so it doesn't fully reset
        the logging basicConfig.

        Example:
            {"incremental": True,
             "loggers": {"": {"level": 30}, "hab.parsers": {"level": 10}},
             "version": 1}
        """
        if filename is None:
            filename = cls.user_prefs_filename(".hab_logging_prefs.json")

        if not filename.exists():
            return False

        with filename.open() as fle:
            cfg = json.load(fle)
            logging.config.dictConfig(cfg)
            return True

    @classmethod
    @abstractmethod
    def check_name(cls, name):
        """Checks if the provided name is valid for this class"""

    @classmethod
    def collapse_paths(cls, paths, ext=None, key=None):
        """Converts a list of paths into a string compatible with the os.

        Args:
            paths: A list of paths that have str called on each of them. If
                a string is passed, it is returned un-modified.
            ext (str, optional): Used to apply special formatting rules based on
                the shell script being written.
            key (str, optional): Used to apply special formatting rules based on
                the environment variable this being used to process.
        """
        if isinstance(paths, str):
            return paths
        return cls.pathsep(ext=ext).join([str(p) for p in paths])

    @classmethod
    def default_ext(cls):
        """Returns the default file extension used on this platform."""
        return cls._default_ext

    @classmethod
    def expand_paths(cls, paths):
        """Converts path strings separated by ``cls.pathsep()`` and lists into
        a list containing Path objects.
        """
        if isinstance(paths, str):
            return [Path(p) for p in paths.split(cls.pathsep())]
        return [Path(p) for p in paths]

    @staticmethod
    def get_platform(name=None):
        """Returns the subclass matching the requested platform name. This can
        be the value returned by sys.platform, BasePlatform.system(), or a name
        returned by a subclass. See `check_name` for details.
        """
        if name is None:
            name = BasePlatform.system()
        # Note: This is a staticmethod because it should always look at its
        # children not the current class's children
        for c in BasePlatform.__subclasses__():
            if c.check_name(name):
                return c

    @classmethod
    def name(cls):
        """The hab name for this platform."""
        return cls._name

    @classmethod
    def path_split(cls, path, pathsep=None):
        """Split a string by pathsep unless that path is a single windows path.
        This is used to detect an windows file path on linux which uses `:` for
        path separator and conflicts with the drive letter specification.

        Args:
            path (str): The string to split.
            pathsep (str, optional): If not specified, `os.pathsep` is used.

        Returns:
            list: A list of individual paths.
        """
        if pathsep is None:
            pathsep = cls.pathsep()

        # If on linux we need to resolve a windows path we can't just use
        # `os.path.pathsep`, check if this is a single windows file path and
        # return it as a list.
        if pathsep == ":" and re_windows_single_path.match(path):
            return [path]

        return path.split(pathsep)

    @classmethod
    def pathsep(cls, ext=None):
        """The path separator used by this platform."""
        return cls._sep

    @classmethod
    def system(cls):
        """Returns the current operating system as `windows`, `osx` or `linux`."""
        if sys.platform == "darwin":
            return "osx"
        if sys.platform == "win32":
            return "windows"
        return "linux"

    @classmethod
    def user_prefs_filename(cls, filename=".hab_user_prefs.json"):
        """Returns the filename that contains the hab user preferences."""
        return Path.home() / filename


class WinPlatform(BasePlatform):
    _default_ext = ".bat"
    _name = "windows"
    _sep = ";"

    @classmethod
    def check_name(cls, name):
        return name in ("win32", "windows")

    @classmethod
    def collapse_paths(cls, paths, ext=None, key=None):
        """Converts a list of paths into a string compatible with the os.

        If ext is `.sh` and key is `PATH` the paths are converted using cygpath
        and `:` is used for pathsep instead of `;`. This is necessary due to cygwin
        converting the PATH env var to linux. It apparently only does this for
        PATH, so other env var's simply have `str` called on them and uses `;`
        for pathsep. See https://cygwin.com/cygwin-ug-net/setup-env.html

        Args:
            paths: A list of paths that have str called on each of them. If
                a string is passed, it is returned un-modified.
            ext (str, optional): Used to apply special formatting rules based on
                the shell script being written.
            key (str, optional): Used to apply special formatting rules based on
                the environment variable this being used to process.
        """
        if isinstance(paths, str):
            return paths
        if ext in (".sh", "") and key == "PATH":
            paths = [cygpath(p) for p in paths]
        else:
            paths = [str(p) for p in paths]
        return cls.pathsep(ext=ext, key=key).join(paths)

    @classmethod
    def pathsep(cls, ext=None, key=None):
        """The path separator used by this platform."""
        if ext in (".sh", "") and key == "PATH":
            # For shwin scripts we should use linux style pathsep
            return ":"
        return cls._sep

    @classmethod
    def user_prefs_filename(cls, filename=".hab_user_prefs.json"):
        """Returns the filename that contains the hab user preferences."""
        return Path(os.path.expandvars("$LOCALAPPDATA")) / filename


class LinuxPlatform(BasePlatform):
    _name = "linux"

    @classmethod
    def check_name(cls, name):
        return name.startswith("linux")


class OsxPlatform(BasePlatform):
    _name = "osx"

    @classmethod
    def check_name(cls, name):
        return name in ("darwin", "osx")


Platform = BasePlatform.get_platform()
"""BasePlatform: Hab uses this variable to handle any platform specific operations
and to know what the current platform is. This allows for centralization of
platform specific code. It also allows the testing suite to switch to other
platforms to prevent the need for a developer to test their changes on each
platform individually, though the CI testing should still run on all platforms.
"""
