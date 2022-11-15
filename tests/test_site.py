import sys
from pathlib import PurePosixPath, PureWindowsPath

import colorama
import pytest

from hab import Site, utils


def test_environment_variables(config_root, monkeypatch):
    paths = [config_root / "site_main.json"]
    monkeypatch.setenv("HAB_PATHS", utils.collapse_paths(paths))
    site = Site()
    assert site.paths == paths

    paths.append(config_root / "site_override.json")
    monkeypatch.setenv("HAB_PATHS", utils.collapse_paths(paths))
    site = Site()
    assert site.paths == paths


class TestResolvePaths:
    def test_path(self, config_root):
        # Check that the correct values are resolved when processing a single result
        paths = [config_root / "site_main.json"]
        site = Site(paths)
        assert site.get("generic_value") is False
        assert "override" not in site
        assert site.get("filename") == ["site_main.json"]

    def test_paths(self, config_root, helpers):
        # Check that values specified by additional files overwrite the previous values
        paths = [config_root / "site_main.json", config_root / "site_override.json"]
        site = Site(paths)
        assert site.get("generic_value") is True
        assert site.get("override") == ["site_override.json"]
        assert site.get("filename") == ["site_override.json"]
        assert site.get("platforms") == ["windows", "linux"]

        # Check that the paths defined in multiple site files are correctly added
        assert len(site.get("config_paths")) == 1
        helpers.check_path_list(
            site.get("config_paths"), [config_root / "configs" / "*"]
        )
        assert len(site.get("distro_paths")) == 2
        helpers.check_path_list(
            site.get("distro_paths"),
            (
                config_root / "distros" / "*",
                config_root / "duplicates" / "distros_1" / "*",
            ),
        )

    def test_paths_reversed(self, config_root, helpers):
        # Check that values specified by additional files overwrite the previous values
        paths = [config_root / "site_override.json", config_root / "site_main.json"]
        site = Site(paths)
        assert site.get("generic_value") is False
        assert site.get("override") == ["site_override.json"]
        assert site.get("filename") == ["site_main.json"]

        # Check that the paths defined in multiple site files are correctly added
        assert len(site.get("config_paths")) == 1
        helpers.check_path_list(
            site.get("config_paths"), [config_root / "configs" / "*"]
        )
        assert len(site.get("distro_paths")) == 2
        helpers.check_path_list(
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


class TestOsSpecific:
    def test_linux(self, monkeypatch, config_root):
        """Check that if "os_specific" is set to true, only vars for the current
        os are resolved."""
        # Simulate running on a linux platform.
        monkeypatch.setattr(sys, "platform", "linux")

        paths = [config_root / "site_os_specific.json"]
        site = Site(paths)

        assert site.get("config_paths") == ["config/path/linux"]
        assert site.get("distro_paths") == ["distro/path/linux"]
        assert site.get("platforms") == ["windows", "linux"]

    def test_mac(self, monkeypatch, config_root):
        """Check that if "os_specific" is set to true, only vars for the current
        os are resolved."""
        # Simulate running on a mac platform.
        monkeypatch.setattr(sys, "platform", "darwin")

        paths = [config_root / "site_os_specific.json"]
        site = Site(paths)

        assert site.get("config_paths") == ["config/path/mac"]
        assert site.get("distro_paths") == ["distro/path/mac"]
        assert site.get("platforms") == ["mac", "linux"]

    def test_win(self, monkeypatch, config_root):
        """Check that if "os_specific" is set to true, only vars for the current
        os are resolved."""
        # Simulate running on a windows platform
        monkeypatch.setattr(sys, "platform", "win32")

        paths = [config_root / "site_os_specific.json"]
        site = Site(paths)

        assert site.get("config_paths") == ["config\\path\\windows"]
        assert site.get("distro_paths") == ["distro\\path\\windows"]
        assert site.get("platforms") == ["windows", "mac"]


class TestPlatformPathMap:
    def test_linux(self, monkeypatch, config_root):
        """For linux check that various inputs are correctly processed."""
        monkeypatch.setattr(sys, "platform", "linux")
        site = Site([config_root / "site_main.json"])

        # Check exact path matches are translated
        out = site.platform_path_map("/usr/local/host/root", platform="linux")
        assert out == "/usr/local/host/root"
        out = site.platform_path_map("/usr/local/host/root/extra", platform="linux")
        assert out == "/usr/local/host/root/extra"

        out = site.platform_path_map("/usr/local/host/root", platform="mac")
        assert out == "/usr/local/mac/host/root"
        out = site.platform_path_map("/usr/local/host/root/extra", platform="mac")
        assert out == "/usr/local/mac/host/root/extra"

        out = site.platform_path_map("/usr/local/host/root", platform="windows")
        assert out == r"c:\host\root"
        out = site.platform_path_map("/usr/local/host/root/extra", platform="windows")
        assert out == r"c:\host\root\extra"

    def test_win(self, monkeypatch, config_root):
        """For windows check that various inputs are correctly processed."""
        monkeypatch.setattr(sys, "platform", "win32")
        site = Site([config_root / "site_main.json"])

        # Check exact path matches are translated
        out = site.platform_path_map(r"c:\host\root", platform="linux")
        assert out == "/usr/local/host/root"
        out = site.platform_path_map(r"c:\host/root/extra", platform="linux")
        assert out == "/usr/local/host/root/extra"
        out = site.platform_path_map("c:/host/root", platform="linux")
        assert out == "/usr/local/host/root"

        out = site.platform_path_map(r"c:\host\root", platform="mac")
        assert out == "/usr/local/mac/host/root"
        out = site.platform_path_map(r"c:\host\root\extra", platform="mac")
        assert out == "/usr/local/mac/host/root/extra"
        out = site.platform_path_map("c:/host/root", platform="mac")
        assert out == "/usr/local/mac/host/root"

        out = site.platform_path_map(r"c:\host\root", platform="windows")
        assert out == r"c:\host\root"
        out = site.platform_path_map(r"c:\host\root\extra", platform="windows")
        assert out == r"c:\host\root\extra"
        out = site.platform_path_map("c:/host/root", platform="windows")
        assert out == r"c:\host\root"


class TestPlatformPathMapDict:
    def assert_main(self, site):
        """Used by several tests to assert site_main.json's "network-mount"
        settings are in use.
        """
        assert site["platform_path_maps"]["network-mount"]["linux"] == PurePosixPath(
            "/mnt/shared_resources"
        )
        assert site["platform_path_maps"]["network-mount"]["mac"] == PurePosixPath(
            "/mnt/mac/shared_resources"
        )
        assert site["platform_path_maps"]["network-mount"][
            "windows"
        ] == PureWindowsPath("\\\\example\\shared_resources")

    def assert_override(self, site):
        """Used by several tests to assert site_override.json's "network-mount"
        settings are in use.
        """
        assert site["platform_path_maps"]["network-mount"]["linux"] == PurePosixPath(
            "/mnt/work/shared_resources"
        )
        assert site["platform_path_maps"]["network-mount"]["mac"] == PurePosixPath(
            "/mnt/work/mac/shared_resources"
        )
        assert site["platform_path_maps"]["network-mount"][
            "windows"
        ] == PureWindowsPath("g:\\work\\shared_resources")

    def test_main(self, config_root):
        """Test that all platform_path_map settings in site_main.json were found."""
        paths = [config_root / "site_main.json"]
        site = Site(paths)

        assert site["platform_path_maps"]["host-root"]["linux"] == PurePosixPath(
            "/usr/local/host/root"
        )
        assert site["platform_path_maps"]["host-root"]["mac"] == PurePosixPath(
            "/usr/local/mac/host/root"
        )
        assert site["platform_path_maps"]["host-root"]["windows"] == PureWindowsPath(
            "c:\\host\\root"
        )

        self.assert_main(site)

    def test_override(self, config_root):
        """Test that all platform_path_map settings in site_override.json were found."""
        paths = [config_root / "site_override.json"]
        site = Site(paths)

        # host-root is not specified in this site file.
        assert "host-root" not in site["platform_path_maps"]

        self.assert_override(site)

    def test_merged(self, config_root):
        """Test that the correct platform_path_map settings are resolved when using
        both site_main.json and site_override.json."""
        paths = [config_root / "site_main.json", config_root / "site_override.json"]
        site = Site(paths)

        # This is only specified in site_main.json
        assert site["platform_path_maps"]["host-root"]["linux"] == PurePosixPath(
            "/usr/local/host/root"
        )
        assert site["platform_path_maps"]["host-root"]["mac"] == PurePosixPath(
            "/usr/local/mac/host/root"
        )
        assert site["platform_path_maps"]["host-root"]["windows"] == PureWindowsPath(
            "c:\\host\\root"
        )

        # The right-most site file's settings are loaded when both have the same keys
        self.assert_override(site)

    def test_reversed(self, config_root):
        """Test that the correct platform_path_map settings are resolved when using
        both site_main.json and site_override.json."""
        paths = [config_root / "site_override.json", config_root / "site_main.json"]
        site = Site(paths)

        # This is only specified in site_main.json
        assert site["platform_path_maps"]["host-root"]["linux"] == PurePosixPath(
            "/usr/local/host/root"
        )
        assert site["platform_path_maps"]["host-root"]["mac"] == PurePosixPath(
            "/usr/local/mac/host/root"
        )
        assert site["platform_path_maps"]["host-root"]["windows"] == PureWindowsPath(
            "c:\\host\\root"
        )

        # The right-most site file's settings are loaded when both have the same keys
        self.assert_main(site)
