import logging

from .. import utils
from .zip_sidecar import DistroFinderZipSidecar

logger = logging.getLogger(__name__)


class DistroFinderZip(DistroFinderZipSidecar):
    """Working with zipped distros extracting the `.hab.json` information from
    inside the .zip file. This is useful when you have direct access to the .zip
    file.

    For `path`, this class uses a .zip `member path`. A member path is the absolute
    path to the .zip joined with the member path of files contained inside the .zip
    file. So if the archive file path is `c:/temp/dist_a_v0.1.zip` and the member is
    `.hab.json`, then the member_path would be `c:/temp/dist_a_v0.1.zip/.hab.json`.

    Note:
        This class should only be used to install distros in the hab download system.

    This expects one file to exist with a specific naming convention:
        - `{distro}_v{version}.zip` contains the entire contents of the distro.
          This should also contain the top level file `.hab.json`. When the distro
          is installed and using hab normally this file will be used. The `.hab.json`
          file's contents are extracted from the zip file and used to initialize the
          `DistroVersion` returned by `self.distro` without being written to disk.
    """

    def __init__(self, root, site=None):
        super().__init__(root, site=site)
        self.glob_str = "*.zip"
        self.hab_filename = ".hab.json"
        self._cache = {}

    def clear_cache(self, persistent=False):
        """Clear cached data in memory. If `persistent` is True then also remove
        cache data from disk if it exists.
        """
        self._cache = {}

    def content(self, path):
        """Returns the distro container for a given path as `pathlib.Path`.

        For this class it returns the path to the .zip file. This .zip file
        contains the contents of the distro and the actual `.hab.json` used
        to create the distro.

        Args:
            path (pathlib.Path): The member path to the `.hab.json` file defining
                the distro.
        """
        return path.parent

    def distro_path_info(self):
        """Generator yielding distro info for each distro found by this distro finder.

        Note:
            This class doesn't use habcache features so cached will always be `False`.

        Yields:
            dirname: Will always be `None`. This class deals with only compressed
                .zip files so there is not a parent directory to work with.
            path: The member path to a given resource.
            cached: Will always be `False`. The path is not stored in a .habcache
                file so this data is not cached across processes.
        """
        for path in self.root.glob(self.glob_str):
            archive = self.archive(path)
            for _, path in self.get_text_files_from_zip(
                archive, members=[self.hab_filename]
            ):
                yield None, path, False

    def get_text_files_from_zip(self, archive, members):
        """Opens the zip archive and yields any member paths that exist in the archive.

        To reduce re-opening the zip archive later this also caches the contents
        of each of these files for later processing in load_path using `archive.read`
        to extract the data as `bytes`.

        Args:
            archive: A `zipfile.ZipFile` like archive to read the file data from.
            members (list): A list of archive members as `str` to yield and cache.

        Yields:
            member (str): The provided member being yielded.
            member_path (pathlib.Path): The member path to the member of the .zip file.
        """
        with archive:
            for member in members:
                if member not in archive.namelist():
                    continue

                data = archive.read(member)
                member_path = self.cast_path(archive.filename) / member
                self._cache[member_path] = data
                yield member, member_path

    def load_path(self, path):
        """Returns a raw dictionary use to create a `DistroVersion` with version set.

        Returns the actual contents of the .zip file's top level file `.hab.json`
        without writing that data to disk. The return is passed to `DistroVersion.load`
        as the data argument. This allows the `DistroFinder` class to directly use
        the data contained inside the .zip archive.

        The version property will always be set in the return. If not defined
        in the `.hab.json` file's contents, its set to the return of `version_for_path`.

        Args:
            path (pathlib.Path): The member path to the `.hab.json` file inside
                of the .zip file.

        Raises:
            KeyError: This method uses the cache populated by `distro_path_info`
                and that method needs to be called before calling this. It is also
                raised if the requested `path` is not defined in the distro.
        """
        logger.debug(f'Loading json: "{path}"')
        data = self._cache[path]
        data = data.decode("utf-8")
        data = utils.loads_json(data, source=path)
        # Pull the version from the sidecar filename if its not explicitly set
        if "version" not in data:
            data["version"] = self.version_for_path(path)
        return data
