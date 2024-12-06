import glob
import json
import logging
import os
import shutil
import sys
from pathlib import Path

import pytest

from hab import DistroMode, Resolver, Site, utils
from hab.distro_finders import df_zip, distro_finder, zip_sidecar
from hab.errors import HabError, InstallDestinationExistsError, InvalidRequirementError
from hab.parsers import DistroVersion
from hab.parsers.lazy_distro_version import LazyDistroVersion


def test_distro_finder_entry_point(config_root):
    """Test edge cases for DistroFinder entry_point processing."""
    paths = [config_root / "site" / "site_distro_finder.json"]
    site = Site(paths)
    distro_paths = site["distro_paths"]
    # Ensure the DistroFinder paths are set correctly when set as EntryPoint
    assert distro_paths[0].root == Path("hab testable") / "download" / "path"
    assert distro_paths[1].root == Path("hab testing") / "downloads"
    # The second path passes the kwargs dict with `site`. This triggers testing
    # when a dict is passed to the entry_point. However site is always set to
    # the current site after a DistroFinder is initialized.
    assert distro_paths[1].site == site


def test_eq():
    a = distro_finder.DistroFinder("path/a")

    assert a == distro_finder.DistroFinder("path/a")
    assert a != distro_finder.DistroFinder("path/b")

    # Test that if the glob_str is different it will not compare equal
    b = distro_finder.DistroFinder("path/a")
    b.glob_str = "*/test.json"
    assert a != b
    # Test that if glob_str attr is missing it will not compare equal
    del b.glob_str
    assert a != b
    # Restore glob_str and the objects will compare equal again
    b.glob_str = "*/.hab.json"
    assert a == b

    # Test that if the root is different it will not compare equal
    b.root = Path(".")
    assert a != b
    # Test that if root attr is missing it will not compare equal
    del b.root
    assert a != b
    # Restore root and the objects will compare equal again
    b.root = Path("path/a")
    assert a == b


@pytest.mark.parametrize(
    "glob_str,count",
    (
        ("{root}/reference*/sh_*", 12),
        ("{root}/reference/*", 0),
        ("{root}/reference_scripts/*/*.sh", 20),
    ),
)
def test_glob_path(config_root, glob_str, count):
    """Ensure `hab.utils.glob_path` returns the expected results."""
    glob_str = glob_str.format(root=config_root)
    # Check against the `glob.glob` result.
    check = sorted([Path(p) for p in glob.glob(glob_str)])

    path_with_glob = Path(glob_str)
    result = sorted(utils.glob_path(path_with_glob))

    assert result == check
    # Sanity check to ensure that the expected results were found by `glob.glob`
    assert len(result) == count


class CheckDistroFinder:
    distro_finder_cls = distro_finder.DistroFinder
    site_template = "site_distro_finder.json"

    def create_resolver(self, zip_root, helpers, tmp_path):
        """Create a hab site for the test."""
        return helpers.render_resolver(
            self.site_template, tmp_path, zip_root=zip_root.as_posix()
        )

    def check_installed(self, a_distro_finder, helpers, tmp_path):
        resolver = self.create_resolver(a_distro_finder.root, helpers, tmp_path)
        finder = resolver.distro_paths[0]
        distro_folder = resolver.site.downloads["install_root"] / "dist_a" / "0.1"

        # The distro is not installed yet
        assert not distro_folder.exists()
        assert not finder.installed(distro_folder)

        # Simulate installing by creating the .hab.json file(contents doesn't matter)
        distro_folder.mkdir(parents=True)
        with (distro_folder / ".hab.json").open("w"):
            pass
        assert finder.installed(distro_folder)

    def check_install(self, a_distro_finder, helpers, tmp_path):
        resolver = self.create_resolver(a_distro_finder.zip_root, helpers, tmp_path)
        dl_finder = resolver.site.downloads["distros"][0]
        assert isinstance(dl_finder, self.distro_finder_cls)
        install_root = resolver.site.downloads["install_root"]

        for di in a_distro_finder.versions.values():
            # Get the downloadable distro
            with resolver.distro_mode_override(DistroMode.Downloaded):
                dl_distro = resolver.find_distro(f"{di.name}=={di.version}")

            # Ensure the finder used to create this distro is set
            assert dl_distro.finder == dl_finder

            dest = install_root / dl_distro.distro_name / str(dl_distro.version)
            assert not dest.exists()
            dl_finder.install(dl_distro.filename, dest)
            assert dest.is_dir()
            assert (dest / ".hab.json").exists()
            assert (dest / "file_a.txt").exists()
            assert (dest / "folder/file_b.txt").exists()

            # Test that if you try to install an already existing distro
            # an exception is raised
            with pytest.raises(
                InstallDestinationExistsError, match="The destination already exists:"
            ) as excinfo:
                dl_finder.install(dl_distro.filename, dest)
            assert excinfo.value.filename == dest

    def check_resolver_install(self, a_distro_finder, helpers, tmp_path, caplog):
        resolver = self.create_resolver(a_distro_finder.zip_root, helpers, tmp_path)
        # NOTE: The `Resolver.install` method defaults dry_run to True so code
        # developers have to opt into actually installing.
        install_root = resolver.site.downloads["install_root"]
        # This dir won't exist until the first non-dry_run install is run.
        assert not install_root.exists()

        # Build testing URI config files.
        config_root = tmp_path / "configs"
        config_root.mkdir()
        with (config_root / "proj_1.json").open("w") as fle:
            json.dump(dict(name="proj_1", distros=["dist_a", "dist_b"]), fle, indent=4)

        # Check that an error is raised if install_root is not set and target
        # is not specified
        resolver.site.downloads.pop("install_root")
        with pytest.raises(HabError, match=r"You must specify target,"):
            resolver.install(target=None)
        resolver.site.downloads["install_root"] = install_root

        # Check only specifying distros, and that they processed in a single resolve
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="hab.resolver"):
            missing = resolver.install(additional_distros=["dist_a", "dist_a==0.1"])
        assert len(missing) == 1
        assert isinstance(missing[0], LazyDistroVersion)
        assert missing[0].name == "dist_a==0.1"
        # Check the dry_run mode logging output
        assert caplog.record_tuples == [
            (
                "hab.resolver",
                logging.WARNING,
                "Dry Run would install distros: dist_a==0.1",
            ),
        ]

        with pytest.raises(InvalidRequirementError):
            resolver.install(additional_distros=["dist_a==0.2", "dist_a==0.1"])

        # Ensure the above installs were all in dry_run mode.
        assert not install_root.exists()

        # Check dry_run=False actually installs a distro
        caplog.clear()
        missing = resolver.install(additional_distros=["dist_a==0.1"], dry_run=False)
        assert (install_root / "dist_a" / "0.1" / ".hab.json").is_file()
        assert (install_root / "dist_a" / "0.1" / "file_a.txt").is_file()
        assert caplog.record_tuples == [
            ("hab.resolver", logging.WARNING, "Installing distros: dist_a==0.1"),
            ("hab.resolver", logging.WARNING, "Installing distro: dist_a==0.1"),
            ("hab.resolver", logging.WARNING, "Installed distros: dist_a==0.1"),
        ]

        # Test passing a URI. This uri doesn't specify a version for dist_a so the
        # newer dist_a==1.0 is installed along side the latest dist_b==0.6.
        caplog.clear()
        missing = resolver.install(uris=["proj_1"], dry_run=False)
        assert (install_root / "dist_a" / "0.1" / ".hab.json").is_file()
        assert (install_root / "dist_a" / "0.1" / "file_a.txt").is_file()
        assert (install_root / "dist_a" / "1.0" / ".hab.json").is_file()
        assert (install_root / "dist_a" / "1.0" / "file_a.txt").is_file()
        assert (install_root / "dist_b" / "0.6" / ".hab.json").is_file()
        assert (install_root / "dist_b" / "0.6" / "file_a.txt").is_file()
        assert caplog.record_tuples == [
            (
                "hab.resolver",
                logging.WARNING,
                "Installing distros: dist_a==1.0, dist_b==0.6",
            ),
            ("hab.resolver", logging.WARNING, "Installing distro: dist_a==1.0"),
            ("hab.resolver", logging.WARNING, "Installing distro: dist_b==0.6"),
            (
                "hab.resolver",
                logging.WARNING,
                "Installed distros: dist_a==1.0, dist_b==0.6",
            ),
        ]

    def check_resolver_install_kwargs(
        self, a_distro_finder, kwargs, installed, helpers, tmp_path, caplog
    ):
        resolver = self.create_resolver(a_distro_finder.zip_root, helpers, tmp_path)

        configs = [
            {"name": "proj_1", "distros": ["dist_a", "dist_b"]},
            {"name": "proj_2", "distros": ["dist_a==0.2", "dist_b==0.5"]},
            {"name": "proj_3", "distros": []},
        ]

        # Build testing URI config files.
        config_root = tmp_path / "configs"
        config_root.mkdir()
        for config in configs:
            with (config_root / f"{config['name']}.json").open("w") as fle:
                json.dump(config, fle, indent=4)

        kwargs["dry_run"] = False
        missing = resolver.install(**kwargs)
        names = sorted([distro.name for distro in missing])
        assert names == installed

    def check_resolver_install_replace(
        self, a_distro_finder, helpers, tmp_path, caplog
    ):
        resolver = self.create_resolver(a_distro_finder.zip_root, helpers, tmp_path)
        install_root = resolver.site.downloads["install_root"]
        data_txt = install_root / "dist_a" / "1.0" / "data.txt"
        file_a = install_root / "dist_a" / "1.0" / "file_a.txt"
        file_a_text = "File A inside the distro."

        # Install the distro
        resolver.install(dry_run=False, additional_distros=["dist_a==1.0"])
        assert file_a.open("r").read() == file_a_text

        # Simulate this version being modified locally or is some how out of date.
        with file_a.open("w") as fle:
            fle.write("Modified text")
        data_txt.unlink()

        # With replace as False, the distro is not modified and is not returned.
        missing = resolver.install(dry_run=False, additional_distros=["dist_a==1.0"])
        assert missing == []
        assert file_a.open("r").read() == "Modified text"
        assert not data_txt.exists()

        # With replace enabled, the distro is removed from disk, re-installed
        # and returned as a missing distro.
        missing = resolver.install(
            replace=True, dry_run=False, additional_distros=["dist_a==1.0"]
        )
        assert [d.name for d in missing] == ["dist_a==1.0"]
        assert file_a.open("r").read() == file_a_text
        assert data_txt.exists()

    def check_resolver_install_existing(
        self, a_distro_finder, helpers, tmp_path, caplog
    ):
        """Check installing additional versions of a distro.

        If a distro has another version installed but that doesn't match the
        install requirements, a suitable distro is resolved and installed as well.
        """
        resolver = self.create_resolver(a_distro_finder.zip_root, helpers, tmp_path)
        # Install a version of dist_a
        missing = resolver.install(dry_run=False, additional_distros=["dist_a==1.0"])
        assert [d.name for d in missing] == ["dist_a==1.0"]

        # Try to install another version of dist_a. This also requires dist_b.
        missing = resolver.install(dry_run=False, additional_distros=["dist_a==0.2"])
        assert sorted([d.name for d in missing]) == ["dist_a==0.2", "dist_b==0.6"]

        # Check that all 3 distros are installed.
        install_root = resolver.site.downloads["install_root"]
        paths = sorted(install_root.glob("*/*/.hab.json"))
        check = [
            install_root / "dist_a" / "0.2" / ".hab.json",
            install_root / "dist_a" / "1.0" / ".hab.json",
            install_root / "dist_b" / "0.6" / ".hab.json",
        ]
        assert paths == check

        # Uninstall dist_b so we can ensure that it gets re-installed because
        # dist_a==0.2 requires it.
        shutil.rmtree(install_root / "dist_b" / "0.6")
        missing = resolver.install(dry_run=False, additional_distros=["dist_a==0.2"])
        assert [d.name for d in missing] == ["dist_b==0.6"]
        assert (install_root / "dist_b" / "0.6" / ".hab.json").exists()


class TestDistroFinder(CheckDistroFinder):
    distro_finder_cls = distro_finder.DistroFinder
    site_template = "site_distro_finder.json"

    def test_content(self, distro_finder_info):
        """Content always returns the parent of the provided path currently."""
        finder = self.distro_finder_cls(distro_finder_info.root)
        # We may want to improve this later, but it works for now
        path = distro_finder_info.root / ".hab.json"
        result = finder.content(path)
        assert result == distro_finder_info.root

    def test_load_path(self, uncached_resolver):
        """Currently load_path for DistroFinder just returns None."""
        finder = distro_finder.DistroFinder("", uncached_resolver.site)
        assert finder.load_path(Path(".")) is None

    def test_installed(self, distro_finder_info, helpers, tmp_path):
        self.check_installed(distro_finder_info, helpers, tmp_path)

    def test_install(self, distro_finder_info, helpers, tmp_path):
        self.check_install(distro_finder_info, helpers, tmp_path)

    def test_clear_cache(self, distro_finder_info):
        """Cover the clear_cache function, which for this class does nothing."""
        finder = self.distro_finder_cls(distro_finder_info.root)
        finder.clear_cache()


class TestZipSidecar(CheckDistroFinder):
    """Tests specific to `DistroFinderZipSidecar`."""

    distro_finder_cls = zip_sidecar.DistroFinderZipSidecar
    site_template = "site_distro_zip_sidecar.json"

    def test_load_path(self, zip_distro_sidecar):
        """The Zip Sidecar reads a .json file next to the zip distro.

        Ensure it's able to read data from the .json file.
        """
        finder = self.distro_finder_cls(zip_distro_sidecar.root)

        # This distro hard codes the version inside the .json file
        data = finder.load_path(zip_distro_sidecar.root / "dist_a_v0.1.hab.json")
        assert data["name"] == "dist_a"
        assert "distros" not in data
        assert data["version"] == "0.1"

        # Test a different distro that doesn't hard code the version
        data = finder.load_path(zip_distro_sidecar.root / "dist_b_v0.5.hab.json")
        assert data["name"] == "dist_b"
        assert "distros" not in data
        assert data["version"] == "0.5"

        # This distro includes required distros
        data = finder.load_path(zip_distro_sidecar.root / "dist_a_v0.2.hab.json")
        assert data["name"] == "dist_a"
        assert data["distros"] == ["dist_b"]
        assert data["version"] == "0.2"

    def test_installed(self, zip_distro_sidecar, helpers, tmp_path):
        self.check_installed(zip_distro_sidecar, helpers, tmp_path)

    def test_install(self, zip_distro_sidecar, helpers, tmp_path):
        self.check_install(zip_distro_sidecar, helpers, tmp_path)


class TestZip(CheckDistroFinder):
    """Tests specific to `DistroFinderZip`."""

    distro_finder_cls = df_zip.DistroFinderZip
    site_template = "site_distro_zip.json"

    def test_content(self, zip_distro):
        finder = df_zip.DistroFinderZip(zip_distro.root)
        # If path is already a .zip file, it is just returned
        path = zip_distro.root / "already_zip.zip"
        result = finder.content(path)
        assert result == path

        # The right most .zip file is returned if path has multiple .zip suffixes.
        path = zip_distro.root / "a.zip" / "b.zip"
        result = finder.content(path)
        assert result == path

        # If a member path is passed, return the right most .zip suffix.
        member_path = path / ".hab.json"
        result = finder.content(member_path)
        assert result == path

        # member paths with nested return the right most .zip suffix.
        member_path = path / "folder" / "sub-folder" / "file.json"
        result = finder.content(member_path)
        assert result == path

        # If no .zip suffix is passed, the original path is returned.
        path = zip_distro.root / "not_an_archive.txt"
        result = finder.content(path)
        assert result == path

    def test_load_path(self, zip_distro):
        """The Zip finder reads a .json file from inside the zip distro file.

        Ensure it's able to read data from the .json file.
        """
        finder = self.distro_finder_cls(zip_distro.root)

        # This distro hard codes the version inside the .json file
        data = finder.load_path(zip_distro.root / "dist_a_v0.1.zip")
        assert data["name"] == "dist_a"
        assert "distros" not in data
        assert data["version"] == "0.1"

        # Test a different distro that doesn't hard code the version
        data = finder.load_path(zip_distro.root / "dist_b_v0.5.zip")
        assert data["name"] == "dist_b"
        assert "distros" not in data
        assert data["version"] == "0.5"

        # This distro includes required distros
        data = finder.load_path(zip_distro.root / "dist_a_v0.2.zip")
        assert data["name"] == "dist_a"
        assert data["distros"] == ["dist_b"]
        assert data["version"] == "0.2"

    def test_zip_get_file_data(self, zip_distro, caplog):
        """Test edge cases for `DistroFinderZip.get_file_data`."""
        finder = df_zip.DistroFinderZip(zip_distro.root)
        assert finder._cache == {}

        # This file doesn't have a .hab.json file inside it
        path = zip_distro.root / "not_valid_v0.1.zip"
        data = finder.get_file_data(path)
        assert data is None
        assert [path / ".hab.json"] == list(finder._cache.keys())
        finder.clear_cache()

        # Check what happens if a member path isn't provided(Just the .zip file path)
        path = zip_distro.root / "dist_a_v0.1.zip"
        member_path = path / ".hab.json"
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger="hab.distro_finders.df_zip"):
            data = finder.get_file_data(path)
        check = [f'Implicitly added member ".hab.json" to path "{member_path}".']
        assert check == [rec.message for rec in caplog.records]
        # The raw data text was read and returned
        assert data == b'{\n    "name": "dist_a",\n    "version": "0.1"\n}'
        assert member_path in finder._cache

        # Test that the cache is returned if populated
        data = "Data already in the cache"
        finder._cache[Path(member_path)] = data
        assert finder.get_file_data(member_path) is data

    def test_installed(self, zip_distro, helpers, tmp_path):
        self.check_installed(zip_distro, helpers, tmp_path)

    def test_install(self, zip_distro, helpers, tmp_path):
        self.check_install(zip_distro, helpers, tmp_path)

    def test_clear_cache(self, distro_finder_info):
        """Test the clear_cache function for this class."""
        finder = self.distro_finder_cls(distro_finder_info.root)
        finder._cache["test"] = "case"
        finder.clear_cache()
        assert finder._cache == {}

    def test_resolver_install(self, zip_distro, helpers, tmp_path, caplog):
        """Test the bulk of the `Resolver.install` method."""
        self.check_resolver_install(zip_distro, helpers, tmp_path, caplog)

    @pytest.mark.parametrize(
        "kwargs,installed",
        (
            (
                {"uris": ["proj_1"]},
                ["dist_a==1.0", "dist_b==0.6"],
            ),
            (
                {"uris": ["proj_1", "proj_2"]},
                ["dist_a==0.2", "dist_a==1.0", "dist_b==0.5", "dist_b==0.6"],
            ),
            (
                {"uris": ["proj_1"], "additional_distros": ["dist_b==0.5"]},
                ["dist_a==1.0", "dist_b==0.5", "dist_b==0.6"],
            ),
            (
                {"uris": ["proj_3"]},
                [],
            ),
            (
                {"uris": ["proj_3"], "additional_distros": ["dist_b"]},
                ["dist_b==0.6"],
            ),
        ),
    )
    def test_resolver_install_kwargs(
        self, zip_distro, kwargs, installed, helpers, tmp_path, caplog
    ):
        """Test how various `Resolver.install` inputs are resolved"""
        self.check_resolver_install_kwargs(
            zip_distro, kwargs, installed, helpers, tmp_path, caplog
        )

    def test_resolver_install_replace(self, zip_distro, helpers, tmp_path, caplog):
        """Test the replace feature of `Resolver.install`.

        Verifies that already installed distros are ignored unless replace is True.
        """
        self.check_resolver_install_replace(zip_distro, helpers, tmp_path, caplog)

    def test_resolver_install_existing(self, zip_distro, helpers, tmp_path, caplog):
        """Test the replace feature of `Resolver.install`.

        Verifies that already installed distros are ignored unless replace is True.
        """
        self.check_resolver_install_existing(zip_distro, helpers, tmp_path, caplog)


# These tests only work if using the `pyXX-s3` tox testing env
@pytest.mark.skipif(
    not os.getenv("VIRTUAL_ENV", "").endswith("-s3"),
    reason="not testing optional s3 cloud",
)
class TestS3(CheckDistroFinder):
    """Tests specific to `DistroFinderS3Zip`.

    Note: All tests should use the `zip_distro_s3` fixture. This ensures that
    any s3 requests are local and also speeds up the test.
    """

    site_template = "site_distro_s3.json"

    class ServerSimulator:
        """Requests server used for testing downloading a partial zip file.

        Based on remotezip test code:
        https://github.com/gtsystem/python-remotezip/blob/master/test_remotezip.py
        """

        def __init__(self, fname):
            self._fname = fname
            self.requested_ranges = []

        def serve(self, request, context):
            import remotezip

            from_byte, to_byte = remotezip.RemoteFetcher.parse_range_header(
                request.headers["Range"]
            )
            self.requested_ranges.append((from_byte, to_byte))

            with open(self._fname, "rb") as f:
                if from_byte < 0:
                    f.seek(0, 2)
                    size = f.tell()
                    f.seek(max(size + from_byte, 0), 0)
                    init_pos = f.tell()
                    content = f.read(min(size, -from_byte))
                else:
                    f.seek(from_byte, 0)
                    init_pos = f.tell()
                    content = f.read(to_byte - from_byte + 1)

            context.headers[
                "Content-Range"
            ] = remotezip.RemoteFetcher.build_range_header(
                init_pos, init_pos + len(content)
            )
            return content

    @property
    def distro_finder_cls(self):
        """Only import this class if the test is not skipped."""
        from hab.distro_finders.s3_zip import DistroFinderS3Zip

        return DistroFinderS3Zip

    def test_load_path(self, zip_distro_s3, helpers, tmp_path, requests_mock):
        """Simulate reading only part of a remote zip file hosted in an aws s3 bucket.

        This doesn't actually connect to an aws s3 bucket, it uses mock libraries
        to simulate the process.
        """
        import boto3

        if sys.version_info.minor <= 7:
            # NOTE: boto3 has dropped python 3.7. Moto changed their context name
            # when they dropped support for python 3.7.
            from moto import mock_s3 as mock_aws
        else:
            from moto import mock_aws

        # Make requests connect to a simulated s3 server that supports the range header
        server = self.ServerSimulator(
            zip_distro_s3.zip_root / "hab-test-bucket" / "dist_a_v0.1.zip"
        )
        requests_mock.register_uri(
            "GET",
            "s3://hab-test-bucket/dist_a_v0.1.zip",
            content=server.serve,
            status_code=200,
        )

        # Create a mock aws setup using moto to test the authorization code
        resolver = self.create_resolver(zip_distro_s3.zip_root, helpers, tmp_path)
        dl_finder = resolver.site.downloads["distros"][0]

        with mock_aws():
            # The LocalS3Client objects don't have all of the s3 properties we
            # require for configuring requests auth. Add them and crate the bucket.
            sess = boto3.Session(region_name="us-east-2")
            conn = boto3.resource("s3", region_name="us-east-2")
            conn.create_bucket(
                Bucket="hab-test-bucket",
                CreateBucketConfiguration={"LocationConstraint": "us-east-2"},
            )
            dl_finder.client.sess = sess
            dl_finder.client.client = sess.client("s3", region_name="us-east-2")

            # Test reading .hab.json from inside a remote .zip file.
            dl_finder = resolver.site.downloads["distros"][0]
            zip_path = dl_finder.root / "dist_a_v0.1.zip"
            archive = dl_finder.archive(zip_path)

            # Check that the filename property is always populated
            assert str(archive.filename) == str(zip_path)

            # Check that we were able to read the data from the archive
            data = dl_finder.load_path(zip_path / ".hab.json")
            assert data["name"] == "dist_a"
            assert data["version"] == "0.1"

        # Verify that remotezip had to make more than one request. This is because
        # the .zip file is larger than `initial_buffer_size`.
        assert len(server.requested_ranges) == 2

    def test_installed(self, zip_distro_s3, helpers, tmp_path):
        self.check_installed(zip_distro_s3, helpers, tmp_path)

    def test_install(self, zip_distro_s3, helpers, tmp_path):
        self.check_install(zip_distro_s3, helpers, tmp_path)

    def test_client(self, zip_distro_s3, helpers, tmp_path):
        """Test `DistroFinderS3Zip.client` edge cases."""
        default_cache_dir = utils.Platform.default_download_cache()
        # Test if `site.downloads["cache_root"]` is not set
        finder = self.distro_finder_cls("s3://hab-test-bucket")
        assert finder.client._local_cache_dir == default_cache_dir

        # Test if `site.downloads["cache_root"]` is set
        resolver = self.create_resolver(zip_distro_s3.root, helpers, tmp_path)
        finder = self.distro_finder_cls("s3://hab-test-bucket", site=resolver.site)
        cache_dir = resolver.site["downloads"]["cache_root"]
        assert finder.client._local_cache_dir == cache_dir

        # Test the client setter
        finder.client = "A custom client"
        assert finder.client == "A custom client"

        # Test init with a custom client
        from cloudpathlib.local import LocalS3Client

        client = LocalS3Client()
        finder = self.distro_finder_cls("s3://hab-test-bucket", client=client)
        assert finder.client == client

    def test_as_posix(self, zip_distro_s3):
        """Cloudpathlib doesn't support `as_posix` a simple str is returned."""
        # Test that as_posix for CloudPath's returns the CloudPath as a str
        finder = self.distro_finder_cls("s3://hab-test-bucket")
        assert finder.as_posix() == "s3://hab-test-bucket"

        # Otherwise it returns a standard pathlib.Path.as_posix value
        finder.root = zip_distro_s3.root
        assert finder.as_posix() == zip_distro_s3.root.as_posix()

    def test_clear_cache(self, zip_distro_s3):
        """Test the clear_cache function for this class."""

        class Archive:
            """Simulated ZipFile class to test that open archives get closed."""

            def __init__(self):
                self.is_open = True

            def close(self):
                self.is_open = False

        class Client:
            """Simulated S3Client to test calling clear_cache on."""

            def __init__(self):
                self.cleared = False

            def clear_cache(self):
                self.cleared = True

        finder = self.distro_finder_cls("s3://hab-test-bucket")
        # Simulate use of the finder
        archive = Archive()
        finder._archives["s3://hab-test-bucket/dist_a_v0.1.zip"] = archive
        finder._cache["test"] = "case"
        finder.client = Client()
        assert archive.is_open
        assert not finder.client.cleared

        # Check that clearing reset the cache variables
        finder.clear_cache()
        assert finder._archives == {}
        assert finder._cache == {}
        # Check that any open archives were closed
        assert not archive.is_open
        # Check that the client was not cleared as persistent is False
        assert not finder.client.cleared

        # Clearing of persistent caches clears the cache
        finder.clear_cache(persistent=True)
        assert finder.client.cleared


# TODO: Break this into separate smaller tests of components for each class not this
@pytest.mark.parametrize(
    "distro_info",
    (
        # "distro_finder_info",
        "zip_distro",
        "zip_distro_sidecar",
    ),
)
def dtest_zip(request, distro_info, helpers, tmp_path):
    # Convert the distro_info parameter to testing values.
    df_cls = df_zip.DistroFinderZip
    hab_json = ".hab.json"
    implements_cache = True
    parent_type = True
    site_filename = "site_distro_zip.json"
    if distro_info == "zip_distro_sidecar":
        df_cls = zip_sidecar.DistroFinderZipSidecar
        hab_json = "{name}_v{ver}.hab.json"
        implements_cache = False
        parent_type = "sidecar"
        site_filename = "site_distro_zip_sidecar.json"
    elif distro_info == "distro_finder_info":
        df_cls = distro_finder.DistroFinder
        implements_cache = False
        parent_type = "directory"
        site_filename = "site_distro_finder.json"
    distro_info = request.getfixturevalue(distro_info)

    site_file = tmp_path / "site.json"
    helpers.render_template(
        site_filename, site_file, zip_root=distro_info.root.as_posix()
    )
    site_distros = tmp_path / "distros"

    check = set([v[:2] for v in distro_info.versions])

    site = Site([site_file])
    resolver = Resolver(site)
    results = set()
    # The correct class was resolved
    df = resolver.distro_paths[0]
    assert type(df) == df_cls

    if implements_cache:
        assert df._cache == {}

    for node in resolver.dump_forest(resolver.distros, attr=None):
        distro = node.node
        if not isinstance(distro, DistroVersion):
            continue

        # Ensure the finder used to create this distro is set
        assert distro.finder == df

        assert distro.filename.name == hab_json.format(
            name=distro.distro_name, ver=distro.version
        )
        if parent_type == "zip":
            # If the parent is a zip, then the parent is a zip file
            assert distro.filename.parent.suffix == ".zip"
            assert distro.filename.parent.is_file()
        elif parent_type == "sidecar":
            # There is a sidecar zip file next to the *.hab.json file
            zip_filename = distro.filename.name.replace(".hab.json", ".zip")
            assert (distro.filename.parent / zip_filename).is_file()
        elif parent_type == "directory":
            assert distro.filename.is_file()
            assert distro.filename.name == ".hab.json"

        if implements_cache:
            assert distro.filename in df._cache

        results.add((distro.distro_name, str(distro.version)))

        # Test the install process extracts all of the files from the zip
        dest = site_distros / distro.distro_name / str(distro.version)
        assert not dest.exists()
        df.install(distro.filename, dest)
        assert dest.is_dir()
        assert (dest / ".hab.json").exists()
        assert (dest / "file_a.txt").exists()
        assert (dest / "folder/file_b.txt").exists()

        # Test that if you try to install an already existing distro
        # an exception is raised
        with pytest.raises(
            InstallDestinationExistsError, match="The destination already exists:"
        ) as excinfo:
            df.install(distro.filename, dest)
        assert excinfo.value.filename == dest

        # Test the installed function
        # Returns True if passed a distro version folder containing a .hab.json
        assert df.installed(dest)
        # It returns False if the .hab.json file doesn't exist
        assert not df.installed(site_distros)

    if implements_cache:
        df.clear_cache()
        assert df._cache == {}

    assert results == check
