import logging
import re
import zipfile

from packaging.version import VERSION_PATTERN

from .. import utils
from .distro_finder import DistroFinder

logger = logging.getLogger(__name__)


class DistroFinderZipSidecar(DistroFinder):
    """Working with zipped distros that have a sidecar `dist_name_v0.0.0.hab.json`
    file. This is useful when it can't extract the `.hab.json` from the .zip file.

    Note:
        This class should only be used to install distros in the hab download system.

    This expects two files to exist with a specific naming convention:
        - `{distro}_v{version}.zip` contains the entire contents of the distro.
          This should also contain the top level file `.hab.json`. When the distro
          is installed and using hab normally this file will be used.
        - `{distro}_v{version}.hab.json` is a copy of the .hab.json file contained
          in the .zip file. This file is used to initialize the `DistroVersion`
          returned by `self.distro` and mainly used to resolve dependent distros
          efficiently when running hab download. It is not used outside of this class.
    """

    version_regex = re.compile(
        rf"(?P<name>.+)_v{VERSION_PATTERN}", flags=re.VERBOSE | re.IGNORECASE
    )
    """Regex used to parse the distro name and version from a file path. This looks
    for a string matching {distro}_v{version}.
    """

    def __init__(self, root, site=None):
        super().__init__(root, site)
        self.glob_str = "*.hab.json"

    def archive(self, zip_path):
        """Returns a `zipfile.Zipfile` like instance for zip_path."""
        return zipfile.ZipFile(zip_path)

    def content(self, path):
        """Returns the distro container for a given path as `pathlib.Path`.

        For this class it returns the path to the sidecar .zip file. This .zip
        file contains the contents of the distro.

        Args:
            path (pathlib.Path): The path to the `.hab.json` file defining the distro.
        """
        # This simply replaces `.hab.json` with `.zip`.
        return path.with_suffix("").with_suffix(".zip")

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
        logger.debug(f"Extracting to {dest} from zip {path}")
        with self.archive(path) as archive:
            members = archive.namelist()
            total = len(members)
            for i, member in enumerate(members):
                logger.debug(f"Extracting file({i}/{total}): {member}")
                archive.extract(member, dest)

    def load_path(self, path):
        """Returns a raw dictionary use to create a `DistroVersion` with version set.

        The return is passed to `DistroVersion.load` as the data argument. This
        allows the `DistroFinder` class to bypass the normal json loading method
        for distros.

        Returns the contents of the sidecar `{distro}_v{version}.hab.json` file.
        The version property will always be set in the return. If not defined
        in the file's contents, its set to the return of `version_for_path`.

        Args:
            path (pathlib.Path): The path to the `.hab.json` file defining the
                distro used to define the returned data.
        """
        logger.debug(f'Loading "{path}"')
        data = utils.load_json_file(path)
        # Pull the version from the sidecar filename if its not explicitly set
        if "version" not in data:
            data["version"] = self.version_for_path(path)
        return data

    def version_for_path(self, path):
        """Returns the version for the given path as a string.

        Args:
            path (pathlib.Path): The path to the `*.hab.json` file defining the
                distro. Uses the `version_regex` to parse the version release.
        """
        return self.version_regex.match(str(path)).group("release")
