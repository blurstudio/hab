def gui():
    """Used to test entry point resolution. Raises an exception for ease of testing."""
    raise NotImplementedError("hab_test_entry_points.gui called successfully")


def gui_alt():
    """Used to test entry point resolution site modification. Raises an exception
    for ease of testing."""
    raise NotImplementedError("hab_test_entry_points.gui_alt called successfully")


def cfg_reduce_env(cfg):
    """Used to test that an entry point is called by raising an exception when
    called. See `tests/site/eps/README.md` for details."""
    raise NotImplementedError(
        "hab_test_entry_points.cfg_reduce_env called successfully"
    )


def cfg_reduce_finalize(cfg):
    """Used to test that an entry point is called by raising an exception when
    called. See `tests/site/eps/README.md` for details."""
    raise NotImplementedError(
        "hab_test_entry_points.cfg_reduce_finalize called successfully"
    )


def site_add_paths(site):
    """Add a couple of extra site paths to hab using `hab.site.add_paths` entry_point."""
    from pathlib import Path

    return [
        Path(__file__).parent / "site" / "eps" / "site_add_paths_a.json",
        Path(__file__).parent / "site" / "eps" / "site_add_paths_b.json",
    ]


def site_add_paths_a(site):
    """Add a couple of extra site paths to hab using `hab.site.add_paths` entry_point."""
    from pathlib import Path

    return [
        Path(__file__).parent / "site" / "eps" / "site_add_paths_c.json",
    ]


def site_finalize(site):
    """Used to test that an entry point is called by raising an exception when
    called. See `tests/site/eps/README.md` for details."""
    raise NotImplementedError("hab_test_entry_points.site_finalize called successfully")


def uri_validate_error(resolver, uri):
    """Used to test that an entry point is called by raising an exception when
    called. See `tests/site/eps/README.md` for details."""
    raise NotImplementedError(
        "hab_test_entry_points.uri_validate_error called successfully"
    )


def uri_validate_project_a(resolver, uri):
    """Used to test hab.uri.validate entry_point."""
    from hab.parsers import HabBase

    # Show how the URI can be modified by validation
    splits = uri.split(HabBase.separator)
    lower = splits[0].lower()
    if lower == "project_a" and splits[0] != lower:
        splits[0] = "project_a"
        uri = HabBase.separator.join(splits)
        return uri


def uri_validate_project_b(resolver, uri):
    """Used to test multiple hab.uri.validate entry_points."""
    from hab.parsers import HabBase

    # Raising an exception stops processing
    if uri == "raise-error":
        raise Exception('URI "raise-error" was used, raising an exception.')

    # Show how the URI can be modified by validation
    splits = uri.split(HabBase.separator)
    upper = splits[0].upper()
    if upper == "PROJECT_B" and splits[0] != upper:
        splits[0] = "PROJECT_B"
        uri = HabBase.separator.join(splits)
        return uri


class CacheVX:
    """Used to validate that the entry_point `hab_habcache_cls` is respected by
    raising an exception when initialized.

    Note: A real example of this class would subclass `hab.cache.Cache`.
    """

    def __init__(self, site):
        raise NotImplementedError("hab_test_entry_points.CacheVX class was used")
