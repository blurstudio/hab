import os
from collections import UserDict
from pathlib import Path

from . import utils
from .merge_dict import MergeDict


class Site(UserDict):
    """Provides site configuration to habitat.

    This dictionary is updated with the contents of each json file stored in paths
    See `habitat.MergeDict` for details.

    Args:
        paths (list, optional): A list of paths to json files defining how
            site should be setup. If not specified, the ``HAB_PATHS`` environment
            variable is used.
    """

    """Provides some default values that are always configured but can be updated."""
    _default_data = {
        "config_paths": [],
        "distro_paths": [],
        "ignored_distros": ["release", "pre"],
    }

    def __init__(self, paths=None):
        self.data = self._default_data.copy()

        if not paths:
            paths = os.getenv("HAB_PATHS", "").split(os.pathsep)
        self.paths = [Path(p) for p in paths if p]

        self.load()

    def _check_reserved_keys(self, data):
        """Validate that data won't override any of the core methods and attributes
        of this class. For example, check that we never replace load, load_file, etc.
        """
        for keys in data.values():
            problems = [key for key in keys if key in self._reserved_keys]
            if problems:
                raise ValueError(
                    f"These keys can not be used for site config: {', '.join(problems)}"
                )

    def load(self):
        """Iterates over each file in self.path. Replacing the value of each key.
        The last file in the list will have its settings applied even if other
        files define them."""
        for path in self.paths:
            self.load_file(path)

    def load_file(self, filename):
        """Load an individual file path and merge its contents onto self.

        Args:
            filename (pathlib.Path): The json file to parse.
        """
        data = utils.load_json_file(filename)

        merger = MergeDict(relative_root=filename.parent)
        merger.validator = self._check_reserved_keys
        merger.update(self, data)

    @property
    def paths(self):
        """A list of ``pathlib.Path``'s processed by load."""
        return self._paths

    @paths.setter
    def paths(self, paths):
        self._paths = paths


# Don't allow configurations to overwrite these values.
Site._reserved_keys = set(dir(Site))
