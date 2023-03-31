import base64
import errno
import json as _json
import os
import re
import sys
import textwrap
import zlib
from abc import ABC, abstractmethod
from collections import UserDict
from collections.abc import KeysView
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

re_windows_single_path = re.compile(r'^([a-zA-Z]:[\\\/][^:;]+)$')
"""A regex that can be used to check if a string is a single windows file path."""


def decode_freeze(txt):
    """Decodes the provided frozen hab string. See `encode_freeze` for
    details on how these strings are encoded. These will start with a version
    identifier `vX:` where X denotes the version it was encoded with."""

    # Extract version information from the string
    try:
        version, txt = txt.split(':', 1)
        if version[0] != 'v':
            raise ValueError("Missing v prefix in version information.")
    except ValueError:
        raise ValueError(
            "Missing freeze version information in format `v0:...`"
        ) from None
    try:
        version = int(version[1:])
    except ValueError:
        raise ValueError(f'Version {version[1:]} is not valid.') from None

    data = txt.encode('ascii')
    data = base64.b64decode(txt)
    if version == 1:
        data = data.decode('utf-8')
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
            label = f'{colorama.Fore.GREEN}{label}{colorama.Style.RESET_ALL}'

    if isinstance(obj, (list, KeysView)):
        rows = []
        obj = [
            dump_object(o, width=width, flat_list=flat_list, color=color) for o in obj
        ]
        if flat_list:
            # combine as many list items as possible onto each line
            # Use non-breaking spaces to prevent word wrap for each item.
            obj = textwrap.wrap(
                ' '.join([x.replace(' ', 'u\00A0') for x in obj]),
                width=width,
                break_long_words=False,
            )
            # Remove those pesky non-breaking spaces
            obj = [x.replace('u\00A0', ' ') for x in obj]
            one_row = ', '.join(obj)
            multi_row = len(obj) > 1
        else:
            # Determine if we can store all of this on a single line within
            # the requested width
            one_row = ', '.join(obj)
            multi_row = len(one_row) > width

        if multi_row:
            rows.append(f'{label}{obj[0]}')
            rows.extend([f'{pad}{o}' for o in obj[1:]])
        else:
            rows = [f'{label}{one_row}']

        return "\n".join(rows)
    elif isinstance(obj, (dict, UserDict)):
        rows = []
        lbl = label
        for k, v in sorted(obj.items()):
            rows.append(
                dump_object(
                    v,
                    label=f'{lbl}{k}:  ',
                    width=width,
                    flat_list=flat_list,
                    color=color,
                )
            )
            lbl = pad
        return "\n".join(rows)
    elif isinstance(obj, PurePath):
        return f"{label}{obj}"
    elif hasattr(obj, 'name'):
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
    width = len(max(body.split('\n'), key=len))
    width = max(len(title), width)
    if color:
        title = f'{colorama.Fore.GREEN}{title}{colorama.Style.RESET_ALL}'
    return f"{title}\n{'-'*width}\n{body}\n{'-'*width}"


def dumps_json(data, **kwargs):
    """Consistent method for calling json.dumps that handles encoding custom
    data objects like NotSet.

    Pyjson5's dump is not as fully featured as python's json, so this ensures
    consistent dumps output as python's json module has more features than
    pyjson5. For example pyjson5 doesn't support indent."""
    kwargs.setdefault('cls', HabJsonEncoder)
    return _json.dumps(data, **kwargs)


def encode_freeze(data, version=None):
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
    """
    if version is None:
        # The current default is 2. Using None makes it easy to control this
        # with a site configuration.
        version = 2

    data = dumps_json(data)
    data = data.encode('utf-8')
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
            # pyjson5 is installed
            e.result['filename'] = str(filename)
            raise e.with_traceback(sys.exc_info()[2]) from None
        except ValueError as e:
            # Using python's native json parser
            msg = f'{e} Filename("{filename}")'
            raise type(e)(msg, e.doc, e.pos).with_traceback(sys.exc_info()[2]) from None
    return data


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


# Make this a singleton so it works like a boolean False for if statements.
NotSet = NotSet()


def path_forward_slash(path):
    """Converts a Path object into a string with forward slashes"""
    return str(path).replace('\\', '/')


class BasePlatform(ABC):
    """Subclasses of BasePlatform are the interface hab uses to handle cross
    platform code.

    The current platform is accessible via hab.utils.Platform which is set by
    calling `BasePlatform.get_platform()`. To change the current platform, set
    the subclass to Platform. `hab.utils.Platform = hab.utils.WinPlatform`
    """

    _name = None
    _sep = ":"

    @classmethod
    @abstractmethod
    def check_name(cls, name):
        """Checks if the provided name is valid for this class"""

    @classmethod
    def collapse_paths(cls, paths):
        """Converts a list of paths into a string compatible with the os."""
        if isinstance(paths, str):
            return paths
        return cls.pathsep().join([str(p) for p in paths])

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
    def pathsep(cls):
        """The path separator used by this platform."""
        return cls._sep

    @classmethod
    def system(cls):
        """Returns the current operating system as `windows`, `mac` or `linux`."""
        if sys.platform == "darwin":
            return "mac"
        if sys.platform == "win32":
            return "windows"
        return "linux"


class WinPlatform(BasePlatform):
    _name = "windows"
    _sep = ";"

    @classmethod
    def check_name(cls, name):
        return name in ("win32", "windows")


class LinuxPlatform(BasePlatform):
    _name = "linux"

    @classmethod
    def check_name(cls, name):
        return name.startswith("linux")


class OsxPlatform(BasePlatform):
    _name = "mac"

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
