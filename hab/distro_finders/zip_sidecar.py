import logging
import re
import zipfile

from packaging.version import VERSION_PATTERN

from .. import utils
from ..errors import InstallDestinationExistsError
from ..parsers.lazy_distro_version import LazyDistroVersion
from .distro_finder import DistroFinder

logger = logging.getLogger(__name__)


class DistroFinderZipSidecar(DistroFinder):
    """Working with zipped distros that have a sidecar `dist_name_v0.0.0.hab.json`
    file. This is useful when it can't extract the `hab_filename` from the .zip file.

    Note:
        This class should only be used to install distros in the hab download system.

    This expects two files to exist with a specific naming convention:
        - `{distro}_v{version}.zip` contains the entire contents of the distro.
          This should also contain the top level file `hab_filename`. When the distro
          is installed and using hab normally this file will be used.
        - `{distro}_v{version}.hab.json` is a copy of the .hab.json file contained
          in the .zip file. This file is used to initialize the `DistroVersion`
          returned by `self.distro` and mainly used to resolve dependent distros
          efficiently when running hab download. It is not used outside of this class.
    """

    version_regex = re.compile(
        rf"(?P<name>[^\\/]+)_v{VERSION_PATTERN}", flags=re.VERBOSE | re.IGNORECASE
    )
    """Regex used to parse the distro name and version from a file path. This looks
    for a string matching {distro}_v{version}.
    """

    def __init__(self, root, site=None):
        super().__init__(root, site)
        self.glob_str = "*.hab.json"

    def archive(self, zip_path, partial=True):
        """Returns a `zipfile.Zipfile` like instance for zip_path.

        Args:
            zip_path (os.PathLike): The path to the zip file to open.
            partial (bool, optional): If True then you only need access to a small
                part of the archive. This is used by sub-classes to optimize access
                to remote zip archives. If True then `HabRemoteZip` will be used
                to only download specific files from the remote archive without
                caching them to disk. If False then remote archives will be fully
                downloaded to disk(using caching) before returning the open archive.
        """
        return zipfile.ZipFile(zip_path)

    def content(self, path):
        """Returns the distro container for a given path as `pathlib.Path`.

        For this class it returns the path to the sidecar .zip file. This .zip
        file contains the contents of the distro.

        Args:
            path (pathlib.Path): The path to the `hab_filename` file defining the distro.
        """
        # This simply replaces `hab_filename` with `.zip`.
        return path.with_suffix("").with_suffix(".zip")

    def content_member(self, path):
        """Splits a member path into content and member.

        Args:
            path (os.PathLike): The member path to split.

        Returns:
            content(os.PathLike): Path to the .zip file.
            member (str): This class always returns `hab_filename`.
        """
        content = self.content(path)
        return content, self.hab_filename

    def distro(self, forest, resolver, path):
        """Returns an `DistroVersion` instance for the distro described py path.

        Args:
            forest: A dictionary of hab.parser objects used to initialize the return.
            resolver (hab.Resolver): The Resolver used to initialize the return.
            path (pathlib.Path): The path to the `hab_filename` file defining the
                distro. This path is loaded into the returned instance.
        """
        distro = LazyDistroVersion(forest, resolver, root_paths=set((self.root,)))
        distro.finder = self
        distro.name, distro.version = self.version_for_path(path)
        distro.distro_name = distro.name
        distro.load(path)
        return distro

    def install(self, path, dest, replace=False):
        """Install the distro into dest.

        Args:
            path (os.PathLike): The path to the `hab_filename` file defining the
                distro. This path is used to find the `content` of the distro.
            dest (pathlib.Path): The directory to install the distro into.
                The contents of the distro are installed into this directory.
                All intermediate directories needed to contain dest will be created.
            replace (bool, optional): If the distro already exists, remove and
                re-copy it. Otherwise raises an Exception.
        """
        path, member = self.content_member(path)
        if (dest / member).exists():
            if not replace:
                raise InstallDestinationExistsError(dest)

        logger.debug(f"Extracting to {dest} from zip {path}")
        with self.archive(path, partial=False) as archive:
            members = archive.namelist()
            total = len(members)
            for i, member in enumerate(members):
                logger.debug(f"Extracting file({i}/{total}): {member}")
                archive.extract(member, dest)
            return True

    def load_path(self, path):
        """Returns a raw dictionary use to create a `DistroVersion` with version set.

        The return is passed to `DistroVersion.load` as the data argument. This
        allows the `DistroFinder` class to bypass the normal json loading method
        for distros.

        Returns the contents of the sidecar `{distro}_v{version}.hab.json` file.
        The version property will always be set in the return. If not defined
        in the file's contents, its set to the return of `version_for_path`.

        Args:
            path (pathlib.Path): The path to the `hab_filename` file defining the
                distro used to define the returned data.
        """
        logger.debug(f'Loading "{path}"')
        data = utils.load_json_file(path)
        # Pull the version from the sidecar filename if its not explicitly set
        if "version" not in data:
            _, data["version"] = self.version_for_path(path)
        return data

    def version_for_path(self, path):
        """Returns the distro name and version for the given path as a string.

        Args:
            path (pathlib.Path): The path to the `*.hab.json` file defining the
                distro. Uses the `version_regex` to parse the version release.
        """
        result = self.version_regex.search(str(path))
        return result.group("name"), result.group("release")
