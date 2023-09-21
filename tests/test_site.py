import sys
from pathlib import PurePosixPath, PureWindowsPath

import colorama
import pytest

from hab import Site, utils


def test_environment_variables(config_root, monkeypatch):
    paths = [config_root / "site_main.json"]
    monkeypatch.setenv("HAB_PATHS", utils.Platform.collapse_paths(paths))
    site = Site()
    assert site.paths == paths

    paths.append(config_root / "site_override.json")
    monkeypatch.setenv("HAB_PATHS", utils.Platform.collapse_paths(paths))
    site = Site()
    assert site.paths == paths


class TestMultipleSites:
    """Check that various combinations of site json files results in the correct
    merged site. The rules are:

    1. The left most site configuration takes precedence for a given item.
    2. For prepend/append operations on lists, the left site file's paths will
    placed on the outside of the the right site file's paths.
    3. For `platform_path_maps`, only the first key is kept and any duplicates
    are discarded.
    """

    def host_left(self):
        return {
            "linux": PurePosixPath("host-linux_left"),
            "windows": PureWindowsPath("host-windows_left"),
        }

    def host_middle(self):
        return {
            "linux": PurePosixPath("host-linux_middle"),
            "windows": PureWindowsPath("host-windows_middle"),
        }

    def host_right(self):
        return {
            "linux": PurePosixPath("host-linux_right"),
            "windows": PureWindowsPath("host-windows_right"),
        }

    def mid(self):
        return {
            "linux": PurePosixPath("mid-linux_middle"),
            "windows": PureWindowsPath("mid-windows_middle"),
        }

    def net(self):
        return {
            "linux": PurePosixPath("net-linux_right"),
            "windows": PureWindowsPath("net-windows_right"),
        }

    def shared_left(self):
        return {
            "linux": PurePosixPath("shared-linux_left"),
            "windows": PureWindowsPath("shared-windows_left"),
        }

    def test_left(self, config_root):
        """Check that site_left.json returns the correct results."""
        paths = [config_root / "site" / "site_left.json"]
        site = Site(paths)

        assert site.get("set_value") == ["left"]
        assert site.get("test_paths") == ["left_prepend", "left_append"]

        check = {"host": self.host_left(), "shared": self.shared_left()}

        assert site.get("platform_path_maps") == check

    def test_middle(self, config_root):
        """Check that site_middle.json returns the correct results."""
        paths = [config_root / "site" / "site_middle.json"]
        site = Site(paths)

        assert site.get("set_value") == ["middle"]
        assert site.get("test_paths") == ["middle_prepend", "middle_append"]

        check = {"host": self.host_middle(), "mid": self.mid()}

        assert site.get("platform_path_maps") == check

    def test_right(self, config_root):
        """Check that site_right.json returns the correct results."""
        paths = [config_root / "site" / "site_right.json"]
        site = Site(paths)

        assert site.get("set_value") == ["right"]
        assert site.get("test_paths") == ["right_prepend", "right_append"]

        check = {"host": self.host_right(), "net": self.net()}

        assert site.get("platform_path_maps") == check

    def test_left_right(self, config_root):
        """Check that site_left.json and site_right.json are merged correctly."""
        paths = [
            config_root / "site" / "site_left.json",
            config_root / "site" / "site_right.json",
        ]
        site = Site(paths)

        assert site.get("set_value") == ["left"]
        assert site.get("test_paths") == [
            "left_prepend",
            "right_prepend",
            "right_append",
            "left_append",
        ]

        check = {
            "host": self.host_left(),
            "net": self.net(),
            "shared": self.shared_left(),
        }

        assert site.get("platform_path_maps") == check

    def test_right_left(self, config_root):
        """Check that reversing site_left.json and site_right.json get merged
        correctly."""
        paths = [
            config_root / "site" / "site_right.json",
            config_root / "site" / "site_left.json",
        ]
        site = Site(paths)

        assert site.get("set_value") == ["right"]
        assert site.get("test_paths") == [
            "right_prepend",
            "left_prepend",
            "left_append",
            "right_append",
        ]

        check = {
            "host": self.host_right(),
            "net": self.net(),
            "shared": self.shared_left(),
        }

        assert site.get("platform_path_maps") == check

    def test_left_middle_right(self, config_root):
        """Check that more than 2 site json files are merged correctly."""
        paths = [
            config_root / "site" / "site_left.json",
            config_root / "site" / "site_middle.json",
            config_root / "site" / "site_right.json",
        ]
        site = Site(paths)

        assert site.get("set_value") == ["left"]
        assert site.get("test_paths") == [
            "left_prepend",
            "middle_prepend",
            "right_prepend",
            "right_append",
            "middle_append",
            "left_append",
        ]

        check = {
            "host": self.host_left(),
            "mid": self.mid(),
            "net": self.net(),
            "shared": self.shared_left(),
        }

        assert site.get("platform_path_maps") == check


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
        paths = [config_root / "site_override.json", config_root / "site_main.json"]
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
        paths = [config_root / "site_main.json", config_root / "site_override.json"]
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
        "{green}Dump of Site{reset}\n",
        "{green}ignored_distros:  {reset}release, pre",
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
        monkeypatch.setattr(utils, "Platform", utils.LinuxPlatform)

        paths = [config_root / "site_os_specific.json"]
        site = Site(paths)

        assert site.get("config_paths") == ["config/path/linux"]
        assert site.get("distro_paths") == ["distro/path/linux"]
        assert site.get("platforms") == ["windows", "linux"]

    def test_osx(self, monkeypatch, config_root):
        """Check that if "os_specific" is set to true, only vars for the current
        os are resolved."""
        # Simulate running on a osx platform.
        monkeypatch.setattr(utils, "Platform", utils.OsxPlatform)

        paths = [config_root / "site_os_specific.json"]
        site = Site(paths)

        assert site.get("config_paths") == ["config/path/osx"]
        assert site.get("distro_paths") == ["distro/path/osx"]
        assert site.get("platforms") == ["osx", "linux"]

    def test_win(self, monkeypatch, config_root):
        """Check that if "os_specific" is set to true, only vars for the current
        os are resolved."""
        # Simulate running on a windows platform
        monkeypatch.setattr(utils, "Platform", utils.WinPlatform)

        paths = [config_root / "site_os_specific.json"]
        site = Site(paths)

        assert site.get("config_paths") == ["config\\path\\windows"]
        assert site.get("distro_paths") == ["distro\\path\\windows"]
        assert site.get("platforms") == ["windows", "osx"]


class TestPlatformPathMap:
    def test_linux(self, monkeypatch, config_root):
        """For linux check that various inputs are correctly processed."""
        monkeypatch.setattr(utils, "Platform", utils.LinuxPlatform)
        site = Site([config_root / "site_main.json"])

        # Check exact path matches are translated
        out = site.platform_path_map("/usr/local/host/root", platform="linux")
        assert out == "/usr/local/host/root"
        out = site.platform_path_map("/usr/local/host/root/extra", platform="linux")
        assert out == "/usr/local/host/root/extra"

        out = site.platform_path_map("/usr/local/host/root", platform="osx")
        assert out == "/usr/local/osx/host/root"
        out = site.platform_path_map("/usr/local/host/root/extra", platform="osx")
        assert out == "/usr/local/osx/host/root/extra"

        out = site.platform_path_map("/usr/local/host/root", platform="windows")
        assert out == r"c:\host\root"
        out = site.platform_path_map("/usr/local/host/root/extra", platform="windows")
        assert out == r"c:\host\root\extra"

    def test_win(self, monkeypatch, config_root):
        """For windows check that various inputs are correctly processed."""
        monkeypatch.setattr(utils, "Platform", utils.WinPlatform)
        site = Site([config_root / "site_main.json"])

        # Check exact path matches are translated
        out = site.platform_path_map(r"c:\host\root", platform="linux")
        assert out == "/usr/local/host/root"
        out = site.platform_path_map(r"c:\host/root/extra", platform="linux")
        assert out == "/usr/local/host/root/extra"
        out = site.platform_path_map("c:/host/root", platform="linux")
        assert out == "/usr/local/host/root"

        out = site.platform_path_map(r"c:\host\root", platform="osx")
        assert out == "/usr/local/osx/host/root"
        out = site.platform_path_map(r"c:\host\root\extra", platform="osx")
        assert out == "/usr/local/osx/host/root/extra"
        out = site.platform_path_map("c:/host/root", platform="osx")
        assert out == "/usr/local/osx/host/root"

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
        assert site["platform_path_maps"]["network-mount"]["osx"] == PurePosixPath(
            "/mnt/osx/shared_resources"
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
        assert site["platform_path_maps"]["network-mount"]["osx"] == PurePosixPath(
            "/mnt/work/osx/shared_resources"
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
        assert site["platform_path_maps"]["host-root"]["osx"] == PurePosixPath(
            "/usr/local/osx/host/root"
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
        assert site["platform_path_maps"]["host-root"]["osx"] == PurePosixPath(
            "/usr/local/osx/host/root"
        )
        assert site["platform_path_maps"]["host-root"]["windows"] == PureWindowsPath(
            "c:\\host\\root"
        )

        # The right-most site file's settings are loaded when both have the same keys
        self.assert_main(site)

    def test_reversed(self, config_root):
        """Test that the correct platform_path_map settings are resolved when using
        both site_main.json and site_override.json."""
        paths = [config_root / "site_override.json", config_root / "site_main.json"]
        site = Site(paths)

        # This is only specified in site_main.json
        assert site["platform_path_maps"]["host-root"]["linux"] == PurePosixPath(
            "/usr/local/host/root"
        )
        assert site["platform_path_maps"]["host-root"]["osx"] == PurePosixPath(
            "/usr/local/osx/host/root"
        )
        assert site["platform_path_maps"]["host-root"]["windows"] == PureWindowsPath(
            "c:\\host\\root"
        )

        # The right-most site file's settings are loaded when both have the same keys
        self.assert_override(site)


class TestEntryPoints:
    def test_empty_site(self, config_root):
        """Test a site not defining any entry points for cli."""
        site = Site([config_root / "site_main.json"])
        entry_points = site.entry_points_for_group("cli")
        assert len(entry_points) == 0

    def test_default(self, config_root):
        """Test a site not defining any entry points for cli."""
        site = Site([config_root / "site_main.json"])
        entry_points = site.entry_points_for_group("cli", default={"test": "case:func"})
        assert len(entry_points) == 1

        # Test that the `test-gui` cli entry point is handled correctly
        ep = entry_points[0]
        assert ep.name == "test"
        assert ep.group == "cli"
        assert ep.value == "case:func"

    @pytest.mark.parametrize(
        "site_files,import_name,fname",
        (
            (["site/site_entry_point_a.json"], "hab_test_entry_points", "gui"),
            (
                ["site/site_entry_point_b.json", "site/site_entry_point_a.json"],
                "hab_test_entry_points",
                "gui_alt",
            ),
            (
                ["site/site_entry_point_a.json", "site/site_entry_point_b.json"],
                "hab_test_entry_points",
                "gui",
            ),
        ),
    )
    def test_site_cli(self, config_root, site_files, import_name, fname):
        """Test a site defining an entry point for cli, possibly multiple times."""
        site = Site([config_root / f for f in site_files])
        entry_points = site.entry_points_for_group("cli")
        assert len(entry_points) == 1

        # Test that the `test-gui` cli entry point is handled correctly
        ep = entry_points[0]
        assert ep.name == "test-gui"
        assert ep.group == "cli"
        assert ep.value == f"{import_name}:{fname}"

        # Load the module's function
        funct = ep.load()

        # The module has now been imported and the correct function was loaded
        assert funct is getattr(sys.modules[import_name], fname)
        with pytest.raises(
            NotImplementedError, match=rf"{import_name}\.{fname} called successfully"
        ):
            funct()
