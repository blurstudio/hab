import colorama
import pytest
from habitat import Site, utils


def test_environment_variables(config_root, monkeypatch):
    paths = [config_root / "site_main.json"]
    monkeypatch.setenv("HAB_PATHS", utils.collapse_paths(paths))
    site = Site()
    assert site.paths == paths

    paths.append(config_root / "site_override.json")
    monkeypatch.setenv("HAB_PATHS", utils.collapse_paths(paths))
    site = Site()
    assert site.paths == paths


def test_resolve_path(config_root):
    # Check that the correct values are resolved when processing a single result
    paths = [config_root / "site_main.json"]
    site = Site(paths)
    assert site.get("generic_value") is False
    assert "override" not in site
    assert site.get("filename") == ["site_main.json"]


def test_resolve_paths(config_root):
    # Check that values specified by additional files overwrite the previous values
    paths = [config_root / "site_main.json", config_root / "site_override.json"]
    site = Site(paths)
    assert site.get("generic_value") is True
    assert site.get("override") == ["site_override.json"]
    assert site.get("filename") == ["site_override.json"]


def test_resolve_paths_reversed(config_root):
    # Check that values specified by additional files overwrite the previous values
    paths = [config_root / "site_override.json", config_root / "site_main.json"]
    site = Site(paths)
    assert site.get("generic_value") is False
    assert site.get("override") == ["site_override.json"]
    assert site.get("filename") == ["site_main.json"]


def test_path_in_raise(config_root):
    paths = [config_root / "site_main.json", config_root / "missing_file.json"]
    with pytest.raises(FileNotFoundError) as excinfo:
        Site(paths)
    assert "No such file or directory:" in str(excinfo.value)
    assert "missing_file.json" in str(excinfo.value)


def test_dump(config_root):
    """utils.dump_object are checked pretty well in test_parsing, here we test
    the colorization settings and ensuring that the desired results are listed
    """
    checks = (
        '{green}Dump of Site{reset}\n',
        '{green}ignored_distros:  {reset}release, pre',
    )

    paths = [config_root / "site_main.json"]
    site = Site(paths)
    assert site.get("colorize") is None

    result = site.dump()
    for check in checks:
        assert (
            check.format(green=colorama.Fore.GREEN, reset=colorama.Style.RESET_ALL)
            in result
        )

    paths = [config_root / "site_override.json"]
    site = Site(paths)
    assert site.get("colorize") is False

    result = site.dump()
    for check in checks:
        assert check.format(green="", reset="") in result
