import logging
import time

import remotezip
from cloudpathlib import CloudPath

from .df_zip import DistroFinderZip

logger = logging.getLogger(__name__)


class DistroFinderCloudZip(DistroFinderZip):
    """Works with zipped distros stored remotely in Amazon S3 buckets.

    Working with zipped distros extracting the `.hab.json` information from
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

    def __init__(self, root, site=None, client=None):
        # # Sub-classes may need to set kwargs before calling super, only set it
        # # if the sub-class hasn't already set it.
        # if not hasattr(self, "kwargs"):
        #     self.kwargs = kwargs
        super().__init__(root, site=site)

    def cast_path(self, path):
        """Return path cast to the `pathlib.Path` like class preferred by this class."""
        return CloudPath(path, client=self.client)

    @property
    def client(self):
        raise NotImplementedError("`client` must be implemented by a sub-class")

    @client.setter
    def client(self, client):
        raise NotImplementedError("`client` must be implemented by a sub-class")

    def credentials(self):
        """Returns the credentials needed for requests to connect to the cloud resource.

        Generates these credentials using the client object.
        """
        raise NotImplementedError("`credentials` must be implemented by a sub-class")

    def archive(self, zip_path):
        """Returns a `zipfile.Zipfile` like instance for zip_path.

        Path should be a aws s3 object url pointing to a .zip file.
        """
        s = time.time()
        logger.debug(f"Connecting to cloud .zip resource: {zip_path}")
        auth, headers = self.credentials()
        ret = remotezip.RemoteZip(zip_path.as_url(), auth=auth, headers=headers)
        ret.filename = zip_path
        e = time.time()
        logger.debug(f"Connected to cloud .zip resource: {zip_path}, took: {e - s}")
        return ret

    def clear_cache(self, persistent=False):
        """Clear cached data in memory. If `persistent` is True then also remove
        cache data from disk if it exists.
        """
        if persistent:
            self.remove_download_cache()
        super().clear_cache(persistent=persistent)

    def content(self, path):
        return path.removesuffix(f"/{self.hab_filename}")

    def install(self, path, dest):
        raise NotImplementedError("Using ZipFile.extract on this is a bad idea")
        # Download zip if not in cache
        # call super on cached zip file
