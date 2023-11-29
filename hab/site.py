import logging
import os
from collections import UserDict
from pathlib import Path, PurePosixPath, PureWindowsPath

from . import utils
from .merge_dict import MergeDict

logger = logging.getLogger(__name__)


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
            color = self.get("colorize", True)

        # Include the paths used to configure this site object
        site_ret = utils.dump_object(
            {"HAB_PATHS": [str(p) for p in self.paths]}, color=color
        )
        # Include all of the resolved site configurations
        ret = []
        for prop, value in self.items():
            if verbosity < 1 and isinstance(value, dict):
                # This is too complex for most site dumps, hide the details behind
                # a higher verbosity setting.
                txt = utils.dump_object(
                    f"Dictionary keys: {len(value)}", label=f"{prop}:  ", color=color
                )
            else:
                txt = utils.dump_object(value, label=f"{prop}:  ", color=color)

            ret.append(txt)

        ret = "\n".join(ret)
        return utils.dump_title("Dump of Site", f"{site_ret}\n{ret}", color=color)

    def entry_points_for_group(self, group, default=None, entry_points=None):
        """Returns a list of importlib_metadata.EntryPoint objects enabled by
        this site config. To import and resolve the defined object call `ep.load()`.

        Args:
            group (str): The name of the group of entry_points to process.
            default (dict, optional): If the entry_point is not defined, return
                the entry points defined by this dictionary. This is the contents
                of the entry_points group, not the entire entry_points dict. For
                example: `{"gui": "hab_gui.cli:gui"}`
            entry_points (dict, optional): Use this dictionary instead of the one
                defined on this Site object.
        """
        # Delay this import to when required. It's faster than pkg_resources but
        # no need to pay the import price for it if you are not using it.
        from importlib_metadata import EntryPoint

        ret = []
        # Use the site defined entry_points if an override dict wasn't provided
        if entry_points is None:
            entry_points = self.get("entry_points", {})

        # Get the entry point definitions, falling back to default if provided
        if group in entry_points:
            ep_defs = entry_points[group]
        else:
            ep_defs = default if default else {}

        # Init the EntryPoint objects
        # While we are using importlib.metadata to create EntryPoints, we are not
        # using it's `entry_points` function. We want the current site configuration
        # to define the entry points being loaded not the installed pip packages.
        for name, value in ep_defs.items():
            ep = EntryPoint(name=name, group=group, value=value)
            ret.append(ep)
        return ret

    def load(self):
        """Iterates over each file in self.path. Replacing the value of each key.
        The last file in the list will have its settings applied even if other
        files define them."""
        # Process the main site files. These are the only ones that can add the
        # `hab.site.add_paths` entry_points.
        for path in reversed(self.paths):
            self.load_file(path)

        # Now that the main site files are handle `hab.site.add_paths` entry_points.
        # This lets you add site json files where you can't hard code the path.
        # For example if you want a site file included in a pip package installed
        # on a host, the path would change depending on the python version being
        # used and if using a editable pip install.
        for ep in self.entry_points_for_group("hab.site.add_paths"):
            logger.debug(f"Running hab.site.add_paths entry_point: {ep}")
            func = ep.load()

            # This entry_point needs to return a list of site file paths as
            # `pathlib.Path` records.
            paths = func(site=self)
            for path in reversed(paths):
                if path in self.paths:
                    logger.debug(f"Path already added, skipping: {path}")
                    continue
                logger.debug(f"Path added by hab.site.add_paths: {path}")
                self.paths.insert(0, path)
                self.load_file(path)

        # Ensure any platform_path_maps are converted to pathlib objects.
        self.standardize_platform_path_maps()

        # Entry_point to allow modification as a final step of loading site files
        self.run_entry_points_for_group("hab.site.finalize", site=self)

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

        mappings = self.get("platform_path_maps", {})
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

    def run_entry_points_for_group(
        self, group, default=None, entry_points=None, **kwargs
    ):
        """Iterates over `entry_points_for_group` calling the resolved object.

        Args:
            group (str): The name of the group of entry_points to process.
            default (dict, optional): If the entry_point is not defined, return
                the entry points defined by this dictionary. This is the contents
                of the entry_points group, not the entire entry_points dict. For
                example: `{"gui": "hab_gui.cli:gui"}`
            entry_points (dict, optional): Use this dictionary instead of the one
                defined on this Site object.
            **kwargs: Any other kwargs are passed to the loaded entry_point record.
        """
        for ep in self.entry_points_for_group(
            group, default=default, entry_points=entry_points
        ):
            logger.debug(f"Running {group} entry_point: {ep}")
            func = ep.load()
            func(**kwargs)

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
