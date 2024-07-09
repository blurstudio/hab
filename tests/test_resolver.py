import os
import sys
from collections import OrderedDict
from pathlib import Path

import anytree
import pytest
from packaging.requirements import Requirement

from hab import NotSet, Resolver, Site, utils
from hab.solvers import Solver


def test_environment_variables(config_root, helpers, monkeypatch):
    """Check that Resolver's init respects the environment variables it uses."""
    config_paths_env = utils.Platform.expand_paths(["a/config/path", "b/config/path"])
    distro_paths_env = utils.Platform.expand_paths(["a/distro/path", "b/distro/path"])
    config_paths_direct = utils.Platform.expand_paths(
        ["z/config/path", "zz/config/path"]
    )
    distro_paths_direct = utils.Platform.expand_paths(
        ["z/distro/path", "zz/distro/path"]
    )

    # Set the config environment variables
    monkeypatch.setenv(
        "HAB_PATHS", utils.Platform.collapse_paths([config_root / "site_env.json"])
    )

    # configured by the environment
    resolver_env = Resolver()
    # configured by passed arguments
    resolver_direct = Resolver(site=Site([config_root / "site_env_direct.json"]))

    # Check the environment configured resolver
    assert resolver_env.config_paths == config_paths_env
    assert resolver_env.distro_paths == distro_paths_env

    # Check the directly configured resolver
    assert resolver_direct.config_paths == config_paths_direct
    assert resolver_direct.distro_paths == distro_paths_direct

    # Check that we properly split string paths into a lists if provided
    resolver_env = Resolver(site=Site([config_root / "site_env.json"]))
    assert resolver_env.config_paths == config_paths_env
    assert resolver_env.distro_paths == distro_paths_env


def test_config(resolver):
    """Spot check a few of the parsed configs to ensure config works."""
    any_resolver = anytree.Resolver()
    default = resolver.configs["default"]
    assert default.name == "default"
    assert any_resolver.get(default, "/default/Sc1").name == "Sc1"
    assert any_resolver.get(default, "/default/Sc11").name == "Sc11"


@pytest.mark.parametrize(
    "path,result,reason",
    (
        ("project_a", "project_a", "Complete root path not found"),
        ("project_a/Sc001", "project_a/Sc001", "Complete secondary path not found"),
        (
            "project_a/Sc001/Animation",
            "project_a/Sc001/Animation",
            "Complete tertiary path not found",
        ),
        (
            "project_a/Sc001/Modeling",
            "project_a/Sc001",
            "Invalid tertiary path not fallen back",
        ),
        (
            "project_a/Sc999/Modeling",
            "project_a",
            "Invalid secondary path not fallen back",
        ),
        (
            "project_a/very/many/paths/resolved",
            "project_a",
            "Invalid n-length path not fallen back",
        ),
        # Default fallback
        ("project_z", "default", "Default root not returned for invalid root."),
        (
            "project_z/Sc001",
            "default",
            "Default root not returned if no matching secondary.",
        ),
        ("project_z/Sc101", "default/Sc1", "Default secondary not returned"),
        (
            "project_z/Sc110",
            "default/Sc11",
            "More specific default secondary not returned",
        ),
        # Leading/trailing separators
        ("/app", "app", "Leading slash not ignored"),
        ("app/", "app", "Trailing slash not sanitized correctly"),
        ("app/case/", "app", "Trailing slash not sanitized correctly"),
    ),
)
def test_closest_config(resolver, path, result, reason):
    """Test that closest_config returns the expected results."""
    assert resolver.closest_config(path).fullpath == result, reason


class TestDumpForest:
    """Test the dump_forest method on resolver"""

    all_uris = [
        "app",
        "  app/aliased",
        "  app/aliased/config",
        "  app/aliased/mod",
        "  app/aliased/mod/config",
        "  app/houdini",
        "  app/houdini/a",
        "  app/houdini/b",
        "  app/maya",
        "  app/maya/2020",
        "  app/maya/2024",
        "default",
        "  default/Sc1",
        "  default/Sc11",
        "not_set",
        "  not_set/child",
        "  not_set/distros",
        "  not_set/empty_lists",
        "  not_set/env1",
        "  not_set/env_path_hab_uri",
        "  not_set/env_path_set",
        "  not_set/env_path_unset",
        "  not_set/no_distros",
        "  not_set/no_env",
        "  not_set/os",
        "optional",
        "  optional/child",
        "place-holder",
        "  place-holder/child",
        "  place-holder/inherits",
        "project_a",
        "  project_a/Sc001",
        "  project_a/Sc001/Animation",
        "  project_a/Sc001/Rigging",
        "verbosity",
        "  verbosity/hidden",
        "  verbosity/inherit",
        "  verbosity/inherit-no",
        "  verbosity/inherit-override",
    ]

    def test_uris_target_default(self, resolver):
        """Test dumping of configs using the default target `hab`. This also
        falls back to global setting."""
        check = list(self.all_uris)
        # Verbosity filter disabled, show all results
        assert resolver._verbosity_target == "hab"
        assert resolver._verbosity_value is None
        result = list(resolver.dump_forest(resolver.configs))
        assert result == check

        # Verbosity filter most verbose
        with utils.verbosity_filter(resolver, verbosity=2):
            result = list(resolver.dump_forest(resolver.configs))
        check.remove("  verbosity/hidden")
        assert result == check

        # Verbosity filter less verbose
        with utils.verbosity_filter(resolver, verbosity=1):
            result = list(resolver.dump_forest(resolver.configs))
        check.remove("  app/maya")
        check.remove("  app/maya/2020")
        check.remove("  app/maya/2024")
        check.remove("verbosity")
        check.remove("  verbosity/inherit")
        assert result == check

        # Verbosity filter least verbose
        with utils.verbosity_filter(resolver, verbosity=0):
            result = list(resolver.dump_forest(resolver.configs))
        check.remove("  verbosity/inherit-override")
        assert result == check

    def test_uris_objs(self, resolver):
        # If attr is "uri" then the uri as a string is returned.
        result = list(resolver.dump_forest(resolver.configs, attr="uri"))
        assert result == self.all_uris
        # If None is passed to attr, then the anytree object is returned
        for i, row in enumerate(resolver.dump_forest(resolver.configs, attr=None)):
            check = self.all_uris[i].strip()
            # Get the uri from the node
            assert check == row.node.uri

    def test_uris_target_hab_gui(self, resolver):
        """Test dumping of configs using the non-default target `hab-gui`. This
        also falls back to global setting."""
        check = list(self.all_uris)
        # Verbosity filter disabled, show all results
        assert resolver._verbosity_target == "hab"
        assert resolver._verbosity_value is None
        with utils.verbosity_filter(resolver, verbosity=None, target="hab-gui"):
            result = list(resolver.dump_forest(resolver.configs))
        assert result == check

        # Verbosity filter most verbose
        with utils.verbosity_filter(resolver, verbosity=2, target="hab-gui"):
            result = list(resolver.dump_forest(resolver.configs))
        assert result == check

        # Verbosity filter less verbose
        with utils.verbosity_filter(resolver, verbosity=1, target="hab-gui"):
            result = list(resolver.dump_forest(resolver.configs))
        check.remove("  verbosity/hidden")
        assert result == check

        # Verbosity filter least verbose
        with utils.verbosity_filter(resolver, verbosity=0, target="hab-gui"):
            result = list(resolver.dump_forest(resolver.configs))
        check.remove("  app/maya")
        check.remove("  app/maya/2020")
        check.remove("  app/maya/2024")
        check.remove("verbosity")
        check.remove("  verbosity/inherit")
        check.remove("  verbosity/inherit-override")
        assert result == check

    def test_distros(self, resolver):
        """Test dumping distros using name attr"""
        result = list(resolver.dump_forest(resolver.distros, attr="name"))
        check = [
            "aliased",
            "  aliased==2.0",
            "aliased_mod",
            "  aliased_mod==1.0",
            "aliased_verbosity",
            "  aliased_verbosity==1.0",
            "all_settings",
            "  all_settings==0.1.0.dev1",
            "houdini18.5",
            "  houdini18.5==18.5.351",
            "houdini19.5",
            "  houdini19.5==19.5.493",
            "maya2020",
            "  maya2020==2020.0",
            "  maya2020==2020.1",
            "maya2024",
            "  maya2024==2024.0",
            "the_dcc",
            "  the_dcc==1.0",
            "  the_dcc==1.1",
            "  the_dcc==1.2",
            "the_dcc_plugin_a",
            "  the_dcc_plugin_a==0.9",
            "  the_dcc_plugin_a==1.0",
            "  the_dcc_plugin_a==1.1",
            "the_dcc_plugin_b",
            "  the_dcc_plugin_b==0.9",
            "  the_dcc_plugin_b==1.0",
            "  the_dcc_plugin_b==1.1",
            "the_dcc_plugin_c",
            "  the_dcc_plugin_c==0.9",
            "  the_dcc_plugin_c==1.0",
            "  the_dcc_plugin_c==1.1",
            "the_dcc_plugin_d",
            "  the_dcc_plugin_d==0.9",
            "  the_dcc_plugin_d==1.0",
            "  the_dcc_plugin_d==1.1",
            "the_dcc_plugin_e",
            "  the_dcc_plugin_e==0.9",
            "  the_dcc_plugin_e==1.0",
            "  the_dcc_plugin_e==1.1",
        ]
        assert result == check

    def test_distros_truncate(self, resolver):
        """Test truncate feature by dumping distros"""
        result = list(resolver.dump_forest(resolver.distros, attr="name", truncate=1))
        check = [
            "aliased",
            "  aliased==2.0",
            "aliased_mod",
            "  aliased_mod==1.0",
            "aliased_verbosity",
            "  aliased_verbosity==1.0",
            "all_settings",
            "  all_settings==0.1.0.dev1",
            "houdini18.5",
            "  houdini18.5==18.5.351",
            "houdini19.5",
            "  houdini19.5==19.5.493",
            "maya2020",
            "  maya2020==2020.0",
            "  maya2020==2020.1",
            "maya2024",
            "  maya2024==2024.0",
            "the_dcc",
            "  the_dcc==1.0",
            "  ...",
            "  the_dcc==1.2",
            "the_dcc_plugin_a",
            "  the_dcc_plugin_a==0.9",
            "  ...",
            "  the_dcc_plugin_a==1.1",
            "the_dcc_plugin_b",
            "  the_dcc_plugin_b==0.9",
            "  ...",
            "  the_dcc_plugin_b==1.1",
            "the_dcc_plugin_c",
            "  the_dcc_plugin_c==0.9",
            "  ...",
            "  the_dcc_plugin_c==1.1",
            "the_dcc_plugin_d",
            "  the_dcc_plugin_d==0.9",
            "  ...",
            "  the_dcc_plugin_d==1.1",
            "the_dcc_plugin_e",
            "  the_dcc_plugin_e==0.9",
            "  ...",
            "  the_dcc_plugin_e==1.1",
        ]
        assert result == check


def test_reduced(resolver, helpers):
    """Check that NotSet is used if no value is provided."""
    cfg = resolver.closest_config("not_set")
    check = ["aliased", "maya2020"]
    helpers.assert_requirements_equal(cfg.distros, check)
    assert cfg.environment_config == NotSet
    assert cfg.inherits is False
    assert cfg.name == "not_set"

    cfg = resolver.closest_config("not_set/child")
    # Not set on the child so should be NotSet(ie doesn't inherit from parent)
    assert cfg.distros == NotSet
    # Settings defined on the child
    config_check = {
        "set": {"TEST": "case", "FMT_FOR_OS": "a{;}b;c:{PATH!e}{;}d"},
        "unset": ["UNSET_VARIABLE"],
    }
    assert cfg.environment_config == config_check
    assert cfg.inherits is True
    assert cfg.name == "child"

    # Verify that a flattened config properly inherits values
    reduced = cfg.reduced(resolver)
    # Inherited from the parent
    helpers.assert_requirements_equal(reduced.distros, check)
    # Values defined on the child are preserved
    assert reduced.environment_config == config_check
    assert reduced.inherits is True
    assert reduced.name == "child"
    assert reduced.uri == "not_set/child"

    # Verify that uri is handled correctly
    uri = "not_set/child/test"
    reduced = cfg.reduced(resolver, uri=uri)
    assert reduced._uri == uri
    assert reduced.uri == uri
    cfg = resolver.closest_config(uri)
    assert cfg._uri is NotSet
    assert cfg.uri == "not_set/child"


def test_resolve_requirements_simple(resolver):
    requirements = {
        "the_dcc": Requirement("the_dcc"),
    }

    # A simple resolve with no recalculations
    resolved = resolver.resolve_requirements(requirements)

    assert len(resolved) == 5
    assert str(resolved["the_dcc"]) == "the_dcc"
    # required by the_dcc==1.2 distro
    assert str(resolved["the_dcc_plugin_a"]) == "the_dcc_plugin_a>=1.0"
    assert str(resolved["the_dcc_plugin_b"]) == "the_dcc_plugin_b>=0.9"
    assert str(resolved["the_dcc_plugin_e"]) == "the_dcc_plugin_e<2.0"
    # required by the_dcc_plugin_a distro
    assert str(resolved["the_dcc_plugin_d"]) == "the_dcc_plugin_d"

    # Check the versions
    assert resolver.find_distro(resolved["the_dcc"]).name == "the_dcc==1.2"
    assert (
        resolver.find_distro(resolved["the_dcc_plugin_a"]).name
        == "the_dcc_plugin_a==1.1"
    )
    assert (
        resolver.find_distro(resolved["the_dcc_plugin_b"]).name
        == "the_dcc_plugin_b==1.1"
    )
    assert (
        resolver.find_distro(resolved["the_dcc_plugin_d"]).name
        == "the_dcc_plugin_d==1.1"
    )
    assert (
        resolver.find_distro(resolved["the_dcc_plugin_e"]).name
        == "the_dcc_plugin_e==1.1"
    )

    # Check that we can pass a string not a Requirement object to find_distro
    assert resolver.find_distro("the_dcc==1.2").name == "the_dcc==1.2"


def test_resolve_requirements_recalculate(resolver):
    """The first pick "the_dcc==1.2" gets discarded by plugin_b. Make sure the correct
    distros are picked.
    """

    # Resolve requires re-calculating
    # Note: To have a stable test, the order of requirements matters. Use an OrderedDict
    requirements = OrderedDict(
        (
            ("the_dcc", Requirement("the_dcc")),
            ("the_dcc_plugin_b", Requirement("the_dcc_plugin_b==0.9")),
        )
    )

    # Use the underlying Solver so we have access to debug resolve_requirements obscures
    solver = Solver(requirements, resolver)
    resolved = solver.resolve()

    # Check that we had to recalculate the resolve at least one time.
    assert solver.redirects_required == 1
    # Check that the_dcc 1.2 had to be ignored, triggering the recalculate
    assert len(solver.invalid) == 1
    assert str(solver.invalid["the_dcc"]) == "the_dcc!=1.2"

    # Check that the resolve is correct
    assert len(resolved) == 5
    assert str(resolved["the_dcc"]) == "the_dcc<1.2"
    # required by the_dcc==1.1 distro
    assert str(resolved["the_dcc_plugin_a"]) == "the_dcc_plugin_a>=1.0"
    assert str(resolved["the_dcc_plugin_b"]) == "the_dcc_plugin_b==0.9"
    assert str(resolved["the_dcc_plugin_e"]) == "the_dcc_plugin_e<2.0"
    # required by the_dcc_plugin_a distro
    assert str(resolved["the_dcc_plugin_d"]) == "the_dcc_plugin_d"

    # Check the versions
    assert resolver.find_distro(resolved["the_dcc"]).name == "the_dcc==1.1"
    assert (
        resolver.find_distro(resolved["the_dcc_plugin_a"]).name
        == "the_dcc_plugin_a==1.1"
    )
    assert (
        resolver.find_distro(resolved["the_dcc_plugin_b"]).name
        == "the_dcc_plugin_b==0.9"
    )
    assert (
        resolver.find_distro(resolved["the_dcc_plugin_d"]).name
        == "the_dcc_plugin_d==1.1"
    )
    assert (
        resolver.find_distro(resolved["the_dcc_plugin_e"]).name
        == "the_dcc_plugin_e==1.1"
    )


@pytest.mark.parametrize(
    "platform,marker",
    (
        ("windows", "Windows"),
        ("linux", "Linux"),
        ("osx", "Darwin"),
    ),
)
def test_resolve_requirements_markers(resolver, platform, marker):
    """Test that platform_system for current host is included or excluded correctly.

    The packaging marker library isn't setup to allow for testing on other
    platforms, so these tests need to pass on all platforms, if running the test
    on this platform, the dependency is included, otherwise it should be ignored.
    """
    check = [
        "the_dcc",
        "the_dcc_plugin_a",
        "the_dcc_plugin_b",
        "the_dcc_plugin_d",
        "the_dcc_plugin_e",
    ]
    # This requirement is only included if running on the target platform
    if utils.Platform.name() == platform:
        check.append("the_dcc_plugin_c")

    # Build requirements utilizing the platform marker.
    requirements = {
        "the_dcc": Requirement("the_dcc"),
        # the_dcc_plugin_c is only included if the current platform matches that.
        "the_dcc_plugin_c": Requirement(
            f"the_dcc_plugin_c;platform_system=='{marker}'"
        ),
    }

    ret = resolver.resolve_requirements(requirements)
    assert set(ret.keys()) == set(check)


@pytest.mark.parametrize(
    "forced,check,check_versions",
    (
        # No forced items
        (
            None,
            ["the_dcc_plugin_a", "the_dcc_plugin_d", "the_dcc_plugin_e<1.0,<2.0"],
            [],
        ),
        # Force
        (
            {
                # Adds a completely new requirement not specified in the config
                "the_dcc_plugin_c": Requirement("the_dcc_plugin_c"),
                # Forces the requirement to a invalid version for the config
                "the_dcc_plugin_e": Requirement("the_dcc_plugin_e==1.1"),
            },
            [
                "the_dcc_plugin_a",
                "the_dcc_plugin_c",
                "the_dcc_plugin_d",
                "the_dcc_plugin_e==1.1",
            ],
            ["the_dcc_plugin_c==1.1", "the_dcc_plugin_e==1.1"],
        ),
    ),
)
def test_forced_requirements(resolver, helpers, forced, check, check_versions):
    requirements = {
        # plugin_a adds an extra dependency outside of the requirements or forced
        "the_dcc_plugin_a": Requirement("the_dcc_plugin_a"),
        "the_dcc_plugin_e": Requirement("the_dcc_plugin_e<1.0"),
    }

    # Check that forced_requirement's are included in the resolved requirements
    resolver_forced = Resolver(
        site=resolver.site,
        forced_requirements=forced,
    )
    resolved = resolver_forced.resolve_requirements(requirements)
    helpers.assert_requirements_equal(resolved, check)
    if forced is None:
        assert resolver_forced.__forced_requirements__ == {}
    else:
        assert resolver_forced.__forced_requirements__.keys() == forced.keys()

        # Ensure this is a deepcopy of forced and ensure the values are equal
        assert resolver_forced.__forced_requirements__ is not forced
        for k, v in resolver_forced.__forced_requirements__.items():
            if sys.version_info.minor == 6:
                # NOTE: packaging>22.0 doesn't support equal checks for Requirement
                # objects. Python 3.6 only has a 21 release, so we have to compare str
                # TODO: Once we drop py3.6 support drop this if statement
                assert str(forced[k]) == str(v)
            else:
                assert forced[k] == v
            assert forced[k] is not v

    # Check that forced_requirements work if the config defines zero distros
    cfg = resolver_forced.resolve("not_set/no_distros")
    versions = cfg.versions
    assert len(versions) == len(check_versions)
    for i, v in enumerate(versions):
        assert v.name == check_versions[i]


def test_forced_requirements_uri(resolver, helpers):
    resolver_forced = Resolver(
        site=resolver.site,
        forced_requirements={"houdini19.5": Requirement("houdini19.5")},
    )
    # We are checking cfg.versions, so these need to be resolved to `==` requirements
    check = ["aliased==2.0", "houdini19.5==19.5.493"]

    def cfg_versions_to_dict(cfg):
        return {v.distro_name: Requirement(v.name) for v in cfg.versions}

    # Forced requirement includes direct distro assignments from the config
    cfg = resolver_forced.resolve("app/aliased")
    versions = cfg_versions_to_dict(cfg)
    helpers.assert_requirements_equal(versions, check)

    # Check that forced requirements are correctly applied even if a config
    # inherits it's distros from a parent config.
    cfg = resolver_forced.resolve("app/aliased/config")
    versions = cfg_versions_to_dict(cfg)
    helpers.assert_requirements_equal(versions, check)


@pytest.mark.parametrize(
    "value,check",
    (
        ("test_string", [Path("test_string")]),
        (f"one{os.pathsep}two", [Path("one"), Path("two")]),
    ),
)
def test_path_expansion(resolver, value, check):
    # Both of these properties end up calling utils.expand_path, so
    # this doubles as a test for that edge case.
    resolver.config_paths = value
    assert resolver.config_paths == check

    resolver.distro_paths = value
    assert resolver.distro_paths == check

    # Check that collapse_paths also works as expected
    assert utils.Platform.collapse_paths("test_string") == str("test_string")


class TestPlatform:
    def test_collapse_paths(self):
        # NOTE: The `ext=".sh", key="PATH"` checks are covering the special case
        # that exists for PATH when using cygwin that doesn't apply to other
        # environment variables. See `utils.WinPlatform.collapse_paths` for details.

        # Passing strings
        arg = "test case"
        assert utils.LinuxPlatform.collapse_paths(arg) == "test case"
        assert utils.OsxPlatform.collapse_paths(arg) == "test case"
        assert utils.WinPlatform.collapse_paths(arg) == "test case"
        assert utils.WinPlatform.collapse_paths(arg, ext="") == "test case"
        assert utils.WinPlatform.collapse_paths(arg, ext=".sh") == "test case"
        assert (
            utils.WinPlatform.collapse_paths(arg, ext=".sh", key="PATH") == "test case"
        )

        # Passing lists that are not paths
        arg = ["test", "case"]
        assert utils.LinuxPlatform.collapse_paths(arg) == "test:case"
        assert utils.OsxPlatform.collapse_paths(arg) == "test:case"
        assert utils.WinPlatform.collapse_paths(arg) == "test;case"
        assert utils.WinPlatform.collapse_paths(arg, ext="") == "test;case"
        assert utils.WinPlatform.collapse_paths(arg, ext=".sh") == "test;case"
        assert (
            utils.WinPlatform.collapse_paths(arg, ext=".sh", key="PATH") == "test:case"
        )

        # Passing lists that are windows paths
        arg = ["c:\\test", "C:\\case"]
        assert utils.LinuxPlatform.collapse_paths(arg) == "c:\\test:C:\\case"
        assert utils.OsxPlatform.collapse_paths(arg) == "c:\\test:C:\\case"
        assert utils.WinPlatform.collapse_paths(arg) == "c:\\test;C:\\case"
        assert utils.WinPlatform.collapse_paths(arg, ext="") == "c:\\test;C:\\case"
        assert utils.WinPlatform.collapse_paths(arg, ext=".sh") == "c:\\test;C:\\case"
        assert (
            utils.WinPlatform.collapse_paths(arg, ext=".sh", key="PATH")
            == "/c/test:/C/case"
        )

        # Passing lists that are linux paths
        arg = ["/test", "/case"]
        assert utils.LinuxPlatform.collapse_paths(arg) == "/test:/case"
        assert utils.OsxPlatform.collapse_paths(arg) == "/test:/case"
        assert utils.WinPlatform.collapse_paths(arg) == "/test;/case"
        assert utils.WinPlatform.collapse_paths(arg, ext="") == "/test;/case"
        assert utils.WinPlatform.collapse_paths(arg, ext=".sh") == "/test;/case"
        assert (
            utils.WinPlatform.collapse_paths(arg, ext=".sh", key="PATH")
            == "/test:/case"
        )

    def test_pathsep(self):
        assert utils.LinuxPlatform.pathsep() == ":"
        assert utils.OsxPlatform.pathsep() == ":"
        assert utils.WinPlatform.pathsep() == ";"
        # Ext is not ignored for windows
        assert utils.WinPlatform.pathsep(ext="") == ";"
        assert utils.WinPlatform.pathsep(ext=".sh") == ";"
        assert utils.WinPlatform.pathsep(ext=".sh", key="PATH") == ":"


def test_cygpath():
    # Check space handling
    assert utils.cygpath("test case") == "test case"
    assert utils.cygpath("test  case") == "test  case"
    assert utils.cygpath("test case", spaces=True) == "test\\ case"
    assert utils.cygpath("test  case", spaces=True) == "test\\ \\ case"
    assert utils.cygpath("more test  case", spaces=True) == "more\\ test\\ \\ case"
    assert utils.cygpath("\\test case\\") == "/test case/"
    assert utils.cygpath("\\test case\\", spaces=True) == "/test\\ case/"

    # Check converting back-slashes to forward-slashes and drive letter handling
    assert utils.cygpath("c:\\test\\case") == "/c/test/case"
    assert utils.cygpath("C:\\test\\case") == "/C/test/case"
    assert utils.cygpath("\\\\server\\share\\dir") == "//server/share/dir"
    assert utils.cygpath("//server/share/dir") == "//server/share/dir"
    assert utils.cygpath("\\\\server/share/dir") == "//server/share/dir"
    assert utils.cygpath("/C/test/case") == "/C/test/case"

    # Check paths with spaces
    def cyg_space(path):
        return utils.cygpath(path, spaces=True)

    assert utils.cygpath("c:\\test\\spaces  are bad") == "/c/test/spaces  are bad"
    assert cyg_space("c:\\test\\spaces  are bad") == "/c/test/spaces\\ \\ are\\ bad"
    assert (
        utils.cygpath("//server/share/spaces  are bad")
        == "//server/share/spaces  are bad"
    )
    assert (
        cyg_space("//server/share/spaces  are bad")
        == "//server/share/spaces\\ \\ are\\ bad"
    )
    assert (
        utils.cygpath("\\\\server/share/spaces  are bad")
        == "//server/share/spaces  are bad"
    )
    assert (
        cyg_space("\\\\server/share/spaces  are bad")
        == "//server/share/spaces\\ \\ are\\ bad"
    )
    assert utils.cygpath("/C/test/spaces  are bad") == "/C/test/spaces  are bad"
    assert cyg_space("/C/test/spaces  are bad") == "/C/test/spaces\\ \\ are\\ bad"


def test_natrual_sort():
    items = ["test10", "test1", "Test3", "test2"]
    # Double check that our test doesn't sort naturally by default
    assert sorted(items) == ["Test3", "test1", "test10", "test2"]

    # Test that natural sort ignores case and groups numbers correctly
    result = utils.natural_sort(items)
    assert result == ["test1", "test2", "Test3", "test10"]

    # Test natural sorting using a custom sort key
    class Node:
        def __init__(self, name):
            super().__init__()
            self.name = name

    nodes = [Node(item) for item in items]
    result = utils.natural_sort(nodes, key=lambda i: i.name)
    check = [n.name for n in result]
    assert check == ["test1", "test2", "Test3", "test10"]


def test_star_import():
    """Check if a import was removed from __init__.py but did not get removed
    from `__all__`.

    Flake8 doesn't seem to capture F822 when run on `__init__.py`. Manually
    attempt a `from hab import *` import to ensure that all of the items listed
    in `__all__` are actually importable.
    """

    # https://stackoverflow.com/a/43059528
    import importlib

    # get a handle on the module
    mdl = importlib.import_module("hab")
    # is there an __all__?  if so respect it
    names = mdl.__dict__["__all__"]

    # Simulate `from hab import *` which can only be done at the module level.
    for k in names:
        # NOTE: If an exception is raised here, you need to remove the attribute
        # name from __all__ or make sure to import the missing object.
        # `AttributeError: module 'hab' has no attribute 'DistroVersion'`
        getattr(mdl, k)


def test_clear_caches(resolver):
    """Test that Resolver.clear_cache works as expected."""
    # Resolver cache is empty
    assert resolver._configs is None
    assert resolver._distros is None

    # Populate resolver cache data
    resolver.resolve("not_set")
    assert isinstance(resolver._configs, dict)
    assert isinstance(resolver._distros, dict)
    assert len(resolver._configs) > 1
    assert len(resolver._distros) > 1

    # Calling clear_caches resets the resolver cache
    resolver.clear_caches()
    assert resolver._configs is None
    assert resolver._distros is None


def test_clear_caches_cached(habcached_resolver):
    """Test that Resolver.clear_cache works when using a habcache."""

    # Populate resolver cache data
    habcached_resolver.resolve("not_set")
    assert isinstance(habcached_resolver.site.cache._cache, dict)
    assert len(habcached_resolver.site.cache._cache)

    habcached_resolver.clear_caches()
    assert habcached_resolver.site.cache._cache is None


def test_uri_validate(config_root):
    """Test the `hab.uri.validate` entry_point."""
    resolver = Resolver(
        site=Site(
            [
                config_root / "site" / "site_ep_uri_validate.json",
                config_root / "site_main.json",
            ]
        )
    )

    # Test if an entry_point raises an exception
    with pytest.raises(
        Exception, match=r'URI "raise-error" was used, raising an exception.'
    ):
        cfg = resolver.resolve("raise-error")

    # "project_a" should be lower cased by the first validator.
    cfg = resolver.resolve("pRoJect_A/CammelCase")
    assert cfg.uri == "project_a/CammelCase"

    # "project_b" should be upper cased by the second validator.
    cfg = resolver.resolve("pRoJect_B/CammelCase")
    assert cfg.uri == "PROJECT_B/CammelCase"

    # Other URI's are not modified by any of the validators.
    cfg = resolver.resolve("proJECT_c/CammelCase")
    assert cfg.uri == "proJECT_c/CammelCase"

    # Test that the default behavior does nothing.
    resolver = Resolver(site=Site([config_root / "site_main.json"]))
    assert resolver.resolve("pRoJect_A/CammelCase").uri == "pRoJect_A/CammelCase"
    assert resolver.resolve("pRoJect_B/CammelCase").uri == "pRoJect_B/CammelCase"
    assert resolver.resolve("proJECT_c/CammelCase").uri == "proJECT_c/CammelCase"


def test_instance(config_root):
    # Check that a resolver instance is created and returned on first call,
    # respecting passed in arguments.
    assert Resolver._instances == {}
    site = Site([config_root / "site_main.json"])
    resolver = Resolver.instance(name="instance_test", site=site, target="test")
    assert resolver is Resolver._instances["instance_test"]
    assert resolver.site is site
    assert resolver._verbosity_target == "test"

    # **kwargs are ignored if you try to access the same instance a again.
    site1 = Site([config_root / "site_main.json", config_root / "site_override.json"])
    resolver1 = Resolver.instance(
        name="instance_test", site=site1, target="ignored_target"
    )
    # The same resolver instance was returned
    assert resolver1 is resolver
    # The kwargs were ignored on the second call
    assert resolver1.site is site
    assert resolver1._verbosity_target == "test"

    # **kwargs are not ignored if requesting a new resolver name.
    resolver2 = Resolver.instance(name="another_ins", site=site1, target="new")
    assert resolver2 is Resolver._instances["another_ins"]
    assert resolver2 is not resolver
    assert resolver2.site is site1
    assert resolver2._verbosity_target == "new"
