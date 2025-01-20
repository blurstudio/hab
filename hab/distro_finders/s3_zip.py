import logging
import sys
from hashlib import sha256

from cloudpathlib import S3Client
from requests_aws4auth import AWS4Auth

from .. import utils
from .cloud_zip import DistroFinderCloudZip

logger = logging.getLogger(__name__)

if sys.version_info.minor <= 7:
    import warnings

    warnings.warn(
        "Boto3 no longer supports python 3.7. You should use a newer python "
        "version for hab install support.",
        DeprecationWarning,
    )


class DistroFinderS3Zip(DistroFinderCloudZip):
    """Works with zipped distros stored remotely in Amazon S3 buckets.

    Working with zipped distros extracting the `hab_filename` information from
    inside the .zip file. This is useful when you have direct access to the .zip
    file.

    For `path`, this class uses a .zip `member path`. A member path is the absolute
    path to the .zip joined with the member path of files contained inside the .zip
    file. So if the archive file path is `c:/temp/dist_a_v0.1.zip` and the member is
    `hab_filename`, then the member_path would be `c:/temp/dist_a_v0.1.zip/.hab.json`.

    Note:
        This class should only be used to install distros in the hab download system.

    This expects one file to exist with a specific naming convention:
        - `{distro}_v{version}.zip` contains the entire contents of the distro.
          This should also contain the top level file `hab_filename`. When the distro
          is installed and using hab normally this file will be used. The `hab_filename`
          file's contents are extracted from the zip file and used to initialize the
          `DistroVersion` returned by `self.distro` without being written to disk.
    """

    def __init__(self, root, site=None, safe=False, client=None, **client_kwargs):
        self.client_kwargs = client_kwargs
        super().__init__(root, site=site, safe=safe, client=client)

    @property
    def client(self):
        try:
            return self._client
        except AttributeError:
            kwargs = self.client_kwargs
            if self.site:
                kwargs["local_cache_dir"] = self.site.downloads["cache_root"]
            else:
                kwargs["local_cache_dir"] = utils.Platform.default_download_cache()
            self._client = S3Client(**kwargs)
        return self._client

    @client.setter
    def client(self, client):
        self._client = client

    def credentials(self):
        """Returns the credentials needed for requests to connect to aws s3 bucket.

        Generates these credentials using the client object.
        """

        try:
            return self._credentials
        except AttributeError:
            pass
        # The `x-amz-content-sha256` header is required for all AWS Signature
        # Version 4 requests. It provides a hash of the request payload. If
        # there is no payload, you must provide the hash of an empty string.
        headers = {"x-amz-content-sha256": sha256(b"").hexdigest()}

        location = self.client.client.get_bucket_location(Bucket=self.root.bucket)[
            "LocationConstraint"
        ]
        auth = AWS4Auth(
            refreshable_credentials=self.client.sess.get_credentials(),
            region=location,
            service="s3",
        )

        self._credentials = (auth, headers)
        return self._credentials
