from pathlib import Path

import pytest

from hab import Resolver, Site
from hab.distro_finders import df_zip, distro_finder, zip_sidecar
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

    if implements_cache:
        distro_finder.clear_cache()
        assert distro_finder._cache == {}

    assert results == check

    # print(check)
    # assert False
