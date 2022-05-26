import errno
import os
import sys
from pathlib import Path

# Attempt to use pyjson5 if its installed, this allows us to add comments
# to the various json documents, but is not required. Trailing comments FTW!
try:
    import pyjson5 as json
    from pyjson5 import Json5Exception as _JsonException
except ImportError:
    import json

    class _JsonException(BaseException):
        """Placeholder exception when pyjson5 is not used. Should never be raised"""


def collapse_paths(paths):
    """Converts a list of paths into a string compatible with the os."""
    if isinstance(paths, str):
        return paths
    return os.pathsep.join([str(p) for p in paths])


def expand_paths(paths):
    """Converts path strings separated by ``os.pathsep`` and lists into
    a list containing Path objects.
    """
    if isinstance(paths, str):
        return [Path(p) for p in paths.split(os.pathsep)]
    return [Path(p) for p in paths]


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


def path_forward_slash(path):
    """Converts a Path object into a string with forward slashes"""
    return str(path).replace('\\', '/')
