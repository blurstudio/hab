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

    def __init__(self, root, site=None, safe=True):
        super().__init__(root, site=site)
        self.glob_str = "*.zip"
        self.hab_filename = ".hab.json"
        self._cache = {}
        self.safe = safe

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
        # If path is already a .zip file return it.
        # Note: We can't concatenate this with `pathlib.Path.parents` so this has
        # to be done separately from the for loop later
        if path.suffix.lower() == ".zip":
            return path

        # Search for the first .zip file extension and return that path if found
        for parent in reversed(path.parents):
            if parent.suffix.lower() == ".zip":
                return parent

        # Otherwise fall back to returning the path
        return path

    def content_member(self, path):
        """Splits a member path into content and member.

        Args:
            path (pathlib.Path): The member path to split.

        Returns:
            content: A `pathlib.Path` like object representing the .zip file.
            member (str): Any remaining member path after the .zip file. If path
                doesn't specify a member, then a empty string is returned.
        """
        content = self.content(path)
        member = str(path.relative_to(content))
        # Return a empty string instead of the relative dot
        if member == ".":
            member = ""
        return content, member

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
            member_path = path / self.hab_filename
            if self.safe:
                # Opening archives on cloud based systems is slow, this allows us
                # to disable checking that the archive actually has a `.hab.json` file.
                data = self.get_file_data(member_path)
                # This should only return None if the archive doesn't contain member
                if data is None:
                    continue

            yield None, member_path, False

    def get_file_data(self, path):
        """Return the data stored inside a member of a .zip file as bytes.

        This is cached and will only open the .zip file to read the contents the
        first time path is used for this instance.

        Args:
            path: The member path to a given resource.
        """
        if path in self._cache:
            return self._cache[path]

        content, member = self.content_member(path)
        with self.archive(content) as archive:
            if member in archive.namelist():
                data = archive.read(member)
            else:
                data = None
            self._cache[path] = data

        return self._cache[path]

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
        data = self.get_file_data(path)
        data = data.decode("utf-8")
        data = utils.loads_json(data, source=path)
        # Pull the version from the sidecar filename if its not explicitly set
        if "version" not in data:
            data["version"] = self.version_for_path(path)
        return data
