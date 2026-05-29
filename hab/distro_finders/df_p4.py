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
