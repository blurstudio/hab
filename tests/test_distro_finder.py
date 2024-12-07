import glob
import logging
from pathlib import Path

import pytest

from hab import Resolver, Site, utils
from hab.distro_finders import df_zip, distro_finder, zip_sidecar
from hab.errors import InstallDestinationExistsError
from hab.parsers import DistroVersion


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


class TestLoadPath:
    """Test the various `DistroFinder.load_path` implementations."""

    def test_distro_finder(self, uncached_resolver):
        """Currently load_path for DistroFinder just returns None."""
        finder = distro_finder.DistroFinder("", uncached_resolver.site)
        assert finder.load_path(Path(".")) is None

    def test_zip_sidecar(self, zip_distro_sidecar):
        """The Zip Sidecar reads a .json file next to the zip distro.

        Ensure it's able to read data from the .json file.
        """
        finder = zip_sidecar.DistroFinderZipSidecar(zip_distro_sidecar.root)

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

    def test_s3(self):
        pass


class TestZip:
    """Tests specific to `DistroFinderZip`."""

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
        finder = df_zip.DistroFinderZip(zip_distro.root)

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


@pytest.mark.parametrize("distro_info", ("zip_distro", "zip_distro_sidecar"))
def test_zip(request, distro_info, helpers, tmp_path):
    # Convert the distro_info parameter to testing values.
    df_cls = df_zip.DistroFinderZip
    hab_json = ".hab.json"
    implements_cache = True
    parent_is_zip = True
    site_filename = "site_distro_zip.json"
    if distro_info == "zip_distro_sidecar":
        df_cls = zip_sidecar.DistroFinderZipSidecar
        hab_json = "{name}_v{ver}.hab.json"
        implements_cache = False
        parent_is_zip = False
        site_filename = "site_distro_zip_sidecar.json"
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
    distro_finder = resolver.distro_paths[0]
    assert type(distro_finder) == df_cls

    if implements_cache:
        assert distro_finder._cache == {}

    for node in resolver.dump_forest(resolver.distros, attr=None):
        distro = node.node
        if not isinstance(distro, DistroVersion):
            continue

        # Ensure the finder used to create this distro is set
        assert distro.finder == distro_finder

        assert distro.filename.name == hab_json.format(
            name=distro.distro_name, ver=distro.version
        )
        if parent_is_zip:
            # If the parent is a zip, then the parent is a zip file
            assert distro.filename.parent.suffix == ".zip"
            assert distro.filename.parent.is_file()
        else:
            # Otherwise there is a sidecar zip file next to the *.hab.json file
            zip_filename = distro.filename.name.replace(".hab.json", ".zip")
            assert (distro.filename.parent / zip_filename).is_file()

        if implements_cache:
            assert distro.filename in distro_finder._cache

        results.add((distro.distro_name, str(distro.version)))

        # Test the install process extracts all of the files from the zip
        dest = site_distros / distro.distro_name / str(distro.version)
        assert not dest.exists()
        distro_finder.install(distro.filename, dest)
        assert dest.is_dir()
        assert (dest / ".hab.json").exists()
        assert (dest / "file_a.txt").exists()
        assert (dest / "folder/file_b.txt").exists()

        # Test that if you try to install an already existing distro
        # an exception is raised
        with pytest.raises(
            InstallDestinationExistsError, match="The destination already exists:"
        ) as excinfo:
            distro_finder.install(distro.filename, dest)
        assert excinfo.value.filename == dest

        # Test the installed function
        # Returns True if passed a distro version folder containing a .hab.json
        assert distro_finder.installed(dest)
        # It returns False if the .hab.json file doesn't exist
        assert not distro_finder.installed(site_distros)

    if implements_cache:
        distro_finder.clear_cache()
        assert distro_finder._cache == {}

    assert results == check
