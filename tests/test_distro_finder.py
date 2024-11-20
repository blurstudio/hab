from pathlib import Path

from hab import Site
from hab.distro_finders.distro_finder import DistroFinder


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
    a = DistroFinder("path/a")

    assert a == DistroFinder("path/a")
    assert a != DistroFinder("path/b")

    # Test that if the glob_str is different it will not compare equal
    b = DistroFinder("path/a")
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
