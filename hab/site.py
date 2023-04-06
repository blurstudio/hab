import os
from collections import UserDict
from pathlib import Path, PurePosixPath, PureWindowsPath

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
        "set": {
            "config_paths": [],
            "distro_paths": [],
            "ignored_distros": ["release", "pre"],
            "platforms": ["windows", "osx", "linux"],
        }
    }

    def __init__(self, paths=None, platform=None):
        if platform is None:
            platform = utils.Platform.name()
        self.platform = platform

        # Add default data to all site instances. Site data is only valid for
        # the current platform, so discard any other platform configurations.
        merger = MergeDict(platforms=[self.platform])
        self.frozen_data = merger.apply_platform_wildcards(self._default_data)

        if not paths:
            paths = os.getenv("HAB_PATHS", "").split(os.pathsep)
        self.paths = [Path(os.path.expandvars(p)).expanduser() for p in paths if p]

        self.load()

    @property
    def data(self):
        return self.frozen_data.get(self.platform)

    def dump(self, verbosity=0, color=None):
        """Return a string of the properties and their values.

        Args:
            verbosity (int, optional): More information is shown with higher values.
            color (bool, optional): Add console colorization to output. If None,
                respect the site property "colorize" defaulting to True.

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
        ret = []
        for prop, value in self.items():
            if verbosity < 1 and isinstance(value, dict):
                # This is too complex for most site dumps, hide the details behind
                # a higher verbosity setting.
                txt = utils.dump_object(
                    f"Dictionary keys: {len(value)}", label=f'{prop}:  ', color=color
                )
            else:
                txt = utils.dump_object(value, label=f'{prop}:  ', color=color)

            ret.append(txt)

        ret = "\n".join(ret)
        return utils.dump_title('Dump of Site', f'{site_ret}\n{ret}', color=color)

    def load(self):
        """Iterates over each file in self.path. Replacing the value of each key.
        The last file in the list will have its settings applied even if other
        files define them."""
        for path in reversed(self.paths):
            self.load_file(path)

        # Ensure any platform_path_maps are converted to pathlib objects.
        self.standardize_platform_path_maps()

    def load_file(self, filename):
        """Load an individual file path and merge its contents onto self.

        Args:
            filename (pathlib.Path): The json file to parse.
        """
        data = utils.load_json_file(filename)

        # Merge the new data into frozen_data
        merger = MergeDict(platforms=[self.platform], relative_root=filename.parent)
        merger.apply_platform_wildcards(data, output=self.frozen_data)

    @property
    def paths(self):
        """A list of ``pathlib.Path``'s processed by load."""
        return self._paths

    @paths.setter
    def paths(self, paths):
        self._paths = paths

    def platform_path_map(self, path, platform=None):
        """Convert the provided path to one valid for the platform.

        Uses mappings defined in `site.get('platform_path_maps', {})` to convert
        path to the target platform.
        """
        if self.platform == "windows":
            path = PureWindowsPath(path)
        else:
            path = PurePosixPath(path)

        mappings = self.get('platform_path_maps', {})
        # Iterate over all mappings and if applicable, apply each of them
        for mapping in mappings.values():
            src = mapping.get(self.platform)
            dest = mapping.get(platform)
            if path == src:
                # The path is the same as the source, no need to try to resolve
                # a relative path, just convert it to the destination
                path = dest
                continue

            # If path is relative to the current src mapping, replace src with
            # dest to generate the updated path
            try:
                relative = path.relative_to(src)
            except ValueError:
                continue
            else:
                path = dest.joinpath(relative)

        return str(path)

    def standardize_platform_path_maps(self):
        """Ensure the mappings defined in platform_path_maps are converted to
        the correct PurePath classes."""
        if "platform_path_maps" not in self.frozen_data[self.platform]:
            return
        mappings = self.frozen_data[self.platform]["platform_path_maps"]

        for mapping in mappings.values():
            for platform in mapping:
                if platform == "windows":
                    mapping[platform] = PureWindowsPath(mapping[platform])
                else:
                    mapping[platform] = PurePosixPath(mapping[platform])
