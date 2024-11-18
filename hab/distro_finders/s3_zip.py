import logging
from hashlib import sha256

import remotezip
from cloudpathlib import CloudPath, S3Client
from requests_aws4auth import AWS4Auth

from .df_zip import DistroFinderZip

logger = logging.getLogger(__name__)


class DistroFinderS3Zip(DistroFinderZip):
    def __init__(
        self, root, site=None, client=None, profile_name=None, **object_filters
    ):
        # Root should not be cast to a pathlib.Path object on this class.
        super().__init__("", site=site)
        # self.object_filters = object_filters
        # bucket_name = root.split("/")[0]
        # self.bucket_name = bucket_name

        self.client = client
        if self.client is None:
            if profile_name:
                self.client = S3Client(profile_name=profile_name)
            else:
                self.client = S3Client()

        self.root = CloudPath(root, client=self.client)

    def _credentials(self):
        """Returns the credentials needed for requests to connect to aws s3 bucket.

        Generates these credentials using the client object.
        """

        try:
            return self.__credentials
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

        self.__credentials = (auth, headers)
        return self.__credentials

    def archive(self, zip_path):
        """Returns a `zipfile.Zipfile` like instance for zip_path.

        Path should be a aws s3 object url pointing to a .zip file.
        """
        logger.debug(f"Connecting to s3 for url: {zip_path}")
        auth, headers = self._credentials()
        ret = remotezip.RemoteZip(zip_path.as_url(), auth=auth, headers=headers)
        ret.filename = zip_path
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
