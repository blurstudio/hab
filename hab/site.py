import os
from collections import UserDict
from pathlib import Path

from . import utils
from .merge_dict import MergeDict


class Site(UserDict):
    """Provides site configuration to hab.

    This dictionary is updated with the contents of each json file stored in paths
    See `hab.MergeDict` for details.

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
        self.paths = [Path(os.path.expandvars(p)).expanduser() for p in paths if p]

        self.load()

    def dump(self, color=None):
        """Return a string of the properties and their values.

        Args:
            environment (bool, optional): Show the environment value.
            environment_config (bool, optional): Show the environment_config value.

        Returns:
            str: The configuration converted to a string
        """
        if color is None:
            color = self.get('colorize', True)

        # Include the paths used to configure this site object
        site_ret = utils.dump_object(
            {'HAB_PATHS': [str(p) for p in self.paths]}, color=color
        )
        # Include all of the resolved site configurations
        ret = utils.dump_object(self, color=color)
        return utils.dump_title('Dump of Site', f'{site_ret}\n{ret}', color=color)

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
        merger.update(self, data)

    @property
    def paths(self):
        """A list of ``pathlib.Path``'s processed by load."""
        return self._paths

    @paths.setter
    def paths(self, paths):
        self._paths = paths
