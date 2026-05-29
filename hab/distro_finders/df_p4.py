import logging
from pathlib import Path

import P4

from .. import utils
from .distro_finder import DistroFinder

logger = logging.getLogger(__name__)


class DistroFinderP4(DistroFinder):
    """Query perforce for client workspaces configured as hab distros.

    Looks for a .hab.json in the root of the workspace. These are treated as
    already installed distros.
    """

    def __init__(self, root="Perforce_Client_Workspaces", site=None):
        super().__init__(root=root, site=site)

    # def distro(self, forest, resolver, path):
    #     """Returns an `DistroVersion` instance for the distro described py path.

    #     Args:
    #         forest: A dictionary of hab.parser objects used to initialize the return.
    #         resolver (hab.Resolver): The Resolver used to initialize the return.
    #         path (pathlib.Path): The path to the `hab_filename` file defining the
    #             distro. This path is loaded into the returned instance.
    #     """
    #     distro = LazyDistroVersion(forest, resolver, root_paths=set((self.root,)))
    #     distro.finder = self
    #     distro.name, distro.version = self.version_for_path(path)
    #     distro.distro_name = distro.name
    #     distro.load(path)
    #     return distro

    def distro_path_info(self):
        """Generator yielding distro info for each distro found by this distro finder.

        Note:
            To use habcache features you must set the site property of this class
            to the desired `hab.site.Site` class. If you don't then it will always
            glob its results and cached will always be False.

        Yields:
            dirname: Each path passed by paths.
            path: The path to a given resource for this dirname.
            cached: If the path was stored in a .habcache file or required using glob.
        """
        # TODO: Implement p4 client path lookup using `p4.iterate_clients()`
        root = Path(r"\\source\dev\mikeh\hab_p4\unreal_hab")
        p4_workspaces = root.glob("*")

        for path in utils.natural_sort(p4_workspaces):
            member_path = path / self.hab_filename
            if member_path.is_file():
                yield None, member_path, False

    # def version_for_path(self, path):
    #     """Returns the distro name and version for the given path as a string.

    #     Args:
    #         path (pathlib.Path): The path to the `*.hab.json` file defining the
    #             distro. Uses the `version_regex` to parse the version release.
    #     """
    #     # TODO: Get the version from p4 or update distro_version.py to support p4 lookup?
    #     # result = self.version_regex.search(str(path))
    #     # return result.group("name"), result.group("release")
    #     return "5.7", "project_name"
