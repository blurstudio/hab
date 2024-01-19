import glob
import json
import logging
from pathlib import Path

from packaging.version import InvalidVersion

from . import utils
from .errors import InvalidVersionError, _IgnoredVersionError

logger = logging.getLogger(__name__)


class Cache:
    """Used to save/restore cached data to speed up initialization of hab.

    The caches are stored per-site file as file next to the site file using the
    same stem name. (Ie by default studio.json would have a cache file called
    studio.habcache).

    If this cache file exists it is used unless enabled is set to False. Cache
    files are useful when you have some sort of CI setup to ensure the cache is
    re-generated using `save_cache` any time you make changes to configs or
    distros that site file references.

    Properties:
        cache_template (dict): The str.format template used to find the cache files.
            This template requires the kwarg `stem`. This template can be overridden
            by the first `site_cache_file_template` property in site.
        enabled (bool): Used to disable using of the cached data forcing a full
            glob and parse of files described by all site files.
    """

    supported_version = 1

    def __init__(self, site):
        self.site = site
        self._cache = None
        self.enabled = True

        # Get the template filename used to find the cache files on disk
        self.cache_template = self.site["site_cache_file_template"][0]

    @property
    def cached_keys(self):
        """A dict of cache keys and how they should be processed.
        {Name of key to cache: ("relative file glob", class used to process)}
        """
        try:
            return self._cached_keys
        except AttributeError:
            pass

        from .parsers import Config, DistroVersion

        self._cached_keys = {
            "config_paths": ("*.json", Config),
            "distro_paths": ("*/.hab.json", DistroVersion),
        }
        return self._cached_keys

    def cache(self, force=False):
        if not self.enabled:
            # If caching is disabled, never attempt to load the cache
            return {}

        if self._cache is not None and not force:
            return self._cache

        self._cache = {}

        # Process caches from right to left. This makes it so the left most
        # cache_file is respected if any paths are duplicated.
        for path in reversed(self.site.paths):
            cache_file = self.site_cache_path(path)
            if cache_file.is_file():
                logger.debug(f"Site cache loading: {cache_file!s}")
                self.load_cache(cache_file)

        # Create a flattened cache removing the glob paths.
        flat_cache = {key: {} for key in self.cached_keys}
        for key in self._cache:
            for values in self._cache.get(key, {}).values():
                flat_cache[key].update(values)

        self._cache["flat"] = flat_cache

        return self._cache

    def clear(self):
        """Reset the cache forcing it to reload the next time its used."""
        if self._cache:
            logger.debug("Site cache contents cleared")
        self._cache = None

    def config_paths(self, flat=False):
        if flat:
            return self.cache().get("flat", {}).get("config_paths", {})
        return self.cache().get("config_paths", {})

    def distro_paths(self, flat=False):
        if flat:
            return self.cache().get("flat", {}).get("distro_paths", {})
        return self.cache().get("distro_paths", {})

    def generate_cache(self, resolver, site_file, version=1):
        """Generate a cache file of the current state defined by this site file.
        This contains the raw values of each URI config and distro file including
        version. If this cache exists it is used instead of searching the file
        system for each path defined in config_paths or distro_paths defined in
        the provided site file. Use this method any time changes are made that
        hab needs to be aware of. Caching is enabled by the existence of this file.
        """
        from .site import Site

        # Indicate the version specification this habcache file conforms to.
        output = {"version": version}

        # read the site file to get paths to process
        temp_site = Site([site_file])
        # Use this to convert platform specific paths to generic variables
        platform_path_key = resolver.site.platform_path_key

        for key, stats in self.cached_keys.items():
            glob_str, cls = stats
            # Process each glob dir defined for this site
            for dirname in temp_site.get(key, []):
                cfg_paths = output.setdefault(key, {}).setdefault(
                    platform_path_key(dirname).as_posix(), {}
                )

                # Add each found hab config to the cache
                for path in sorted(glob.glob(str(dirname / glob_str))):
                    path = Path(path)
                    try:
                        data = cls(forest={}, resolver=resolver)._load(
                            path, cached=False
                        )
                    except (
                        InvalidVersion,
                        InvalidVersionError,
                        _IgnoredVersionError,
                    ) as error:
                        logger.debug(str(error))
                    else:
                        cfg_paths[platform_path_key(path).as_posix()] = data

        return output

    @classmethod
    def iter_cache_paths(cls, name, paths, cache, glob_str=None, include_path=True):
        """Yields path information stored in the cache falling back to glob if
        not cached.

        Yields:
            dirname: Each path stored in paths.
            path
        """
        for dirname in paths:
            dn_posix = dirname.as_posix()
            cached = dn_posix in cache
            if cached:
                logger.debug(f"Using cache for {name} dir: {dn_posix}")
                paths = cache[dn_posix]
            else:
                logger.debug(f"Using glob for {name} dir: {dirname}")
                # Fallback to globing the file system
                if glob_str:
                    paths = sorted(glob.glob(str(dirname / glob_str)))
                else:
                    paths = []
            if not include_path:
                yield dirname, None, cached
            else:
                for path in paths:
                    yield dirname, path, cached

    def load_cache(self, filename, platform=None):
        """For each glob dir add or replace the contents. If a previous cache
        has the same glob dir, it's cache is ignored. This expects that
        load_cache is called from right to left for each path in `self.site.path`.
        """

        def cache_to_platform(cache, mappings):
            """Restore the cross-platform variables to current platform paths."""
            ret = {}
            for glob_str, files in cache.items():
                new_glob = glob_str.format(**mappings)
                new_glob = Path(new_glob).as_posix()
                new_files = {}
                for key, value in files.items():
                    new_key = key.format(**mappings)
                    new_key = Path(new_key).as_posix()
                    new_files[new_key] = value
                ret[new_glob] = new_files

            return ret

        if platform is None:
            platform = utils.Platform.name()

        contents = utils.load_json_file(filename)

        # If the cache was saved by a newer habcache system, warn that we are
        # unable to load the cache but don't raise an exception
        if contents["version"] > self.supported_version:
            logger.warning(
                f"File is using a unsupported habcache version {contents['version']}. "
                f"Only versions > {self.supported_version} are supported, ignoring {filename}"
            )
            return

        mappings = self.site.get("platform_path_maps", {})
        mappings = {key: value[platform] for key, value in mappings.items()}
        for key in self.cached_keys:
            if key in contents:
                cache = cache_to_platform(contents[key], mappings)
                self._cache.setdefault(key, {}).update(cache)

    def save_cache(self, resolver, site_file, version=1):
        cache_file = self.site_cache_path(site_file)
        cache = self.generate_cache(resolver, site_file, version=version)

        with cache_file.open("w") as fle:
            json.dump(cache, fle, indent=4, cls=utils.HabJsonEncoder)
        return cache_file

    def site_cache_path(self, path):
        """Returns the name of the cache file for the given site file."""
        return path.parent / self.cache_template.format(stem=path.stem)
