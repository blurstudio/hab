import os
from pathlib import Path


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


def path_forward_slash(path):
    """Converts a Path object into a string with forward slashes"""
    return str(path).replace('\\', '/')
