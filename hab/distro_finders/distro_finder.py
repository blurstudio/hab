import logging
import pathlib
import shutil

from colorama import Fore, Style

from .. import utils
from ..parsers.distro_version import DistroVersion

logger = logging.getLogger(__name__)


class DistroFinder:
    """A class used to find and install distros if required.

    The class `DistroFinder` is used by hab in normal operation. Most of the the
    other sub-classes like `DistroFinderZip` are used by the hab download system
    to download and extract distro versions into the expected folder structure.

    The aliases(programs) hab launches are normally not designed to load files
    from inside of a .zip file so the contents of the distro need to be expanded
    into a directory structure the alias can process.
    """

    def __init__(self, root, site=None):
        self.root = utils.Platform.normalize_path(self.cast_path(root))
        self.glob_str = "*/.hab.json"
        self.site = site

    def __eq__(self, other):
        if not hasattr(other, "root"):
            return False
        if not hasattr(other, "glob_str"):
            return False
        return self.root == other.root and self.glob_str == other.glob_str

    def __str__(self):
        return f"{self.root}"

    def as_posix(self):
        """Returns the root path as a posix style string."""
        return self.root.as_posix()

    def cast_path(self, path):
        """Return path cast to the `pathlib.Path` like class preferred by this class."""
        return pathlib.Path(path)

    def clear_cache(self, persistent=False):
        """Clear cached data in memory. If `persistent` is True then also remove
        cache data from disk if it exists.
        """
        pass

    def content(self, path):
        """Returns the distro container for a given path as `pathlib.Path`.

        The default implementation returns the directory containing the `.hab.json`
        file but subclasses may return other objects like .zip files.

        Args:
            path (pathlib.Path): The path to the `.hab.json` file defining the distro.
        """
        return path.parent

    def distro(self, forest, resolver, path):
        """Returns an `DistroVersion` instance for the distro described py path.

        Args:
            forest: A dictionary of hab.parser objects used to initialize the return.
            resolver (hab.Resolver): The Resolver used to initialize the return.
            path (pathlib.Path): The path to the `.hab.json` file defining the
                distro. This path is loaded into the returned instance.
        """
        distro = DistroVersion(forest, resolver, root_paths=set((self.root,)))
        data = self.load_path(path)
        if data:
            distro.version = data["version"]
        distro.load(path, data=data)
        distro.finder = self
        return distro

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
        # Handle if site has not been set, this does not use habcache.
        if not self.site:
            logger.debug("site not set, using direct glob.")
            for path in utils.glob_path(self.root / self.glob_str):
                yield self.root, self.cast_path(path), False

        # Otherwise use the site cache to yield the results
        cache = self.site.cache.distro_paths()
        for dirname, path, cached in self.site.cache.iter_cache_paths(
            "distro_paths", [self.root], cache, self.glob_str
        ):
            yield dirname, path, cached

    def dump(self, verbosity=0, color=None, width=80):
        """Return string representation of this object with various verbosity."""
        if verbosity > 1:
            if not color:
                return f"{self.root} [{type(self).__name__}]"
            return f"{self.root} {Fore.CYAN}[{type(self).__name__}]{Style.RESET_ALL}"
        return str(self)

    def install(self, path, dest):
        """Install the distro into dest.

        Args:
            path (pathlib.Path): The path to the `.hab.json` file defining the
                distro. This path is used to find the `content` of the distro.
            dest (pathlib.Path or str): The directory to install the distro into.
                The contents of the distro are installed into this directory.
                All intermediate directories needed to contain dest will be created.
        """
        path = self.content(path)
        logger.debug(f"Installing to {dest} from source {path}")
        shutil.copytree(path, dest)

    def load_path(self, path):
        """Returns a raw dictionary use to create a `DistroVersion` or None.

        The return is passed to `DistroVersion.load` as the data argument. This
        allows the `DistroFinder` class to bypass the normal json loading method
        for distros.

        This is called by `distro` and used by sub-classes to more efficiently
        load the distro dictionary when possible. The default class returns `None`.

        Args:
            path (pathlib.Path): The path to the `.hab.json` file defining the
                distro used to define the returned data.
        """
        # By default return None to use the `DistroVersion._load` method.
        return None

    @property
    def site(self):
        """A `hab.site.Site` instance used to enable habcache."""
        return self._site

    @site.setter
    def site(self, site):
        self._site = site
