import sys
from pathlib import Path

import colorama
import pytest

from hab import Site, utils


def check_path_list(paths, checks):
    """Check that a list of path strings match a list of Path objects."""
    for i, check in enumerate(checks):
        assert Path(paths[i]) == check


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
    assert site.get("platforms") == ["windows", "mac", "linux"]

    # Check that the paths defined in multiple site files are correctly added
    assert len(site.get("config_paths")) == 1
    check_path_list(site.get("config_paths"), [config_root / "configs" / "*"])
    assert len(site.get("distro_paths")) == 2
    check_path_list(
        site.get("distro_paths"),
        (
            config_root / "distros" / "*",
            config_root / "duplicates" / "distros_1" / "*",
        ),
    )


def test_resolve_paths_reversed(config_root):
    # Check that values specified by additional files overwrite the previous values
    paths = [config_root / "site_override.json", config_root / "site_main.json"]
    site = Site(paths)
    assert site.get("generic_value") is False
    assert site.get("override") == ["site_override.json"]
    assert site.get("filename") == ["site_main.json"]

    # Check that the paths defined in multiple site files are correctly added
    assert len(site.get("config_paths")) == 1
    check_path_list(site.get("config_paths"), [config_root / "configs" / "*"])
    assert len(site.get("distro_paths")) == 2
    check_path_list(
        site.get("distro_paths"),
        (
            config_root / "duplicates" / "distros_1" / "*",
            config_root / "distros" / "*",
        ),
    )


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


def test_os_specific_linux(monkeypatch, config_root):
    """Check that if "os_specific" is set to true, only vars for the current
    os are resolved."""
    # Simulate running on a linux platform.
    monkeypatch.setattr(sys, "platform", "linux")

    paths = [config_root / "site_os_specific.json"]
    site = Site(paths)

    assert site.get("config_paths") == ["config/path/linux"]
    assert site.get("distro_paths") == ["distro/path/linux"]
    assert site.get("platforms") == ["windows", "linux"]


def test_os_specific_mac(monkeypatch, config_root):
    """Check that if "os_specific" is set to true, only vars for the current
    os are resolved."""
    # Simulate running on a mac platform.
    monkeypatch.setattr(sys, "platform", "darwin")

    paths = [config_root / "site_os_specific.json"]
    site = Site(paths)

    assert site.get("config_paths") == ["config/path/mac"]
    assert site.get("distro_paths") == ["distro/path/mac"]
    assert site.get("platforms") == ["mac", "linux"]


def test_os_specific_win(monkeypatch, config_root):
    """Check that if "os_specific" is set to true, only vars for the current
    os are resolved."""
    # Simulate running on a windows platform
    monkeypatch.setattr(sys, "platform", "win32")

    paths = [config_root / "site_os_specific.json"]
    site = Site(paths)

    assert site.get("config_paths") == ["config\\path\\windows"]
    assert site.get("distro_paths") == ["distro\\path\\windows"]
    assert site.get("platforms") == ["windows", "mac"]
