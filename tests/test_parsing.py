import copy
import json
import re
import sys
from pathlib import Path

import anytree
import pytest
import setuptools_scm
from packaging.version import Version

from hab import NotSet, utils
from hab.errors import (
    DuplicateJsonError,
    HabError,
    InvalidVersionError,
    ReservedVariableNameError,
    _IgnoredVersionError,
)
from hab.parsers import Config, DistroVersion, FlatConfig


class TestLoadJsonFile:
    """Tests various conditions when using `hab.utils.load_json_file` to ensure
    expected output.
    """

    def test_missing(self, tmpdir):
        """If the file doesn't exist, the exception includes the missing filename."""
        path = Path(tmpdir) / "missing.json"
        with pytest.raises(
            FileNotFoundError, match="No such file or directory:"
        ) as excinfo:
            utils.load_json_file(path)
        assert Path(excinfo.value.filename) == path

    def test_binary(self, tmpdir):
        """If attempting to read a binary file, filename is included in exception.

        This is a problem we run into rarely where a text file gets
        replaced/generated with a binary file containing noting but a lot of null bytes.
        """
        path = Path(tmpdir) / "binary.json"
        # Create a binary test file containing multiple binary null values.
        with path.open("wb") as fle:
            fle.write(b"\x00" * 32)

        # Detect if using pyjson5 or not
        native_json = False
        try:
            import pyjson5
        except ImportError:
            native_json = True
        if native_json:
            exc_type = json.decoder.JSONDecodeError
        else:
            exc_type = pyjson5.pyjson5.Json5IllegalCharacter

        with pytest.raises(exc_type) as excinfo:
            utils.load_json_file(path)

        if native_json:
            # If built-in json was used, check that filename was appended to the message
            assert f'Filename("{path}")' in str(excinfo.value)
        else:
            # If pyjson5 was used, check that the filename was added to the result dict
            assert f"{{'filename': {str(path)!r}}}" in str(excinfo.value)

    def test_config_load(self, uncached_resolver):
        cfg = Config({}, uncached_resolver)

        # Loading a directory raises a FileNotFoundError
        with pytest.raises(FileNotFoundError):
            cfg.load(".")

        # Loading a non-existent file path raises a FileNotFoundError
        with pytest.raises(FileNotFoundError):
            cfg.load("invalid_path.json")


def test_distro_parse(config_root, resolver):
    """Check that a distro json can be parsed correctly"""
    forest = {}
    app = DistroVersion(forest, resolver)
    path = config_root / "distros" / "all_settings" / "0.1.0.dev1" / ".hab.json"
    app.load(path)
    check = json.load(path.open())
    # Add dynamic alias settings like "distro" to the testing reference.
    # That should never be defined in the raw alias json data.
    app.standardize_aliases(check["aliases"])

    assert "{name}=={version}".format(**check) == app.name
    assert Version(check["version"]) == app.version
    assert check["environment"] == app.environment_config

    assert check["aliases"] == app.aliases
    assert ["all_settings"] == app.context

    # Verify that if the json file doesn't have "version" defined it uses the
    # parent directory as its version.
    app = DistroVersion(forest, resolver)
    path = config_root / "distros" / "maya2020" / "2020.0" / ".hab.json"
    app.load(path)
    check = json.load(path.open())

    # tests\distros\maya\2020.0\.hab.json does not have "version"
    # defined. This allows us to test that DistroVersion will pull the
    # version number from the parent directory not the json file.
    assert "version" not in check
    assert app.version == Version("2020.0")


def test_distro_exceptions(config_root, uncached_resolver):
    """Check that a exception is raised if you define "distro" on an alias."""
    forest = {}
    app = DistroVersion(forest, uncached_resolver)
    # This file is used to test this feature and otherwise should be ignored.
    path = config_root / "distros" / "all_settings" / "0.1.0.dev1" / "invalid.hab.json"
    with pytest.raises(
        HabError, match=r'The "distro" value on an alias dict is reserved.'
    ):
        app.load(path)


def test_distro_version_resolve(config_root, resolver, helpers, monkeypatch, tmpdir):
    """Check the various methods for DistroVersion.version to be populated."""

    # Test that `.hab_version.txt` is respected if it exists.
    forest = {}
    app = DistroVersion(forest, resolver)
    path = config_root / "distros_version" / "txt_file" / ".hab.json"
    app.load(path)
    assert app.version == Version("1.7")

    # Test that an error is raised if the version could not be determined
    path = config_root / "distros_version" / "not_scm" / ".hab.json"
    with pytest.raises(InvalidVersionError, match=r"Hab was unable to determine"):
        app.load(path)

    # Test that an nice error is raised if setuptools_scm is not installed
    with monkeypatch.context() as m:
        # Simulate that setuptools-scm is not installed
        m.setitem(sys.modules, "setuptools_scm", None)
        with pytest.raises(
            InvalidVersionError,
            match=r"\[ModuleNotFoundError\] import of setuptools_scm halted",
        ):
            app.load(path)

    # Test that setuptools_scm is able to resolve the version.
    # This env var forces setuptools_scm to this version so we don't have to
    # create a git repo to test that get_version is called correctly.
    with monkeypatch.context() as m:
        m.setenv("SETUPTOOLS_SCM_PRETEND_VERSION", "1.9")
        app.load(path)
        assert app.version == Version("1.9")

    # Check that we add debug info to arbitrary setuptools_scm Exceptions.
    def get_ver(*args, **kwargs):
        raise OSError("Simulate a arbitrary error in setuptools_scm.get_version")

    with monkeypatch.context() as m:
        m.setattr(setuptools_scm, "get_version", get_ver)
        with pytest.raises(InvalidVersionError, match=r"\[OSError\] Simulate"):
            app.load(path)

    # Test that if the dirname matches `resolver.ignored`, the folder is
    # skipped by raising an _IgnoredVersionError exception.
    path = config_root / "distros_version" / "release" / ".hab.json"
    with pytest.raises(
        _IgnoredVersionError, match=r"its dirname is in the ignored list"
    ):
        app.load(path)

    # Check that `resolver.ignored` is also respected for arbitrary
    # setuptools_scm Exceptions.
    with monkeypatch.context() as m:
        m.setattr(setuptools_scm, "get_version", get_ver)
        with pytest.raises(
            _IgnoredVersionError, match=r"its dirname is in the ignored list"
        ):
            app.load(path)


def test_distro_version(resolver):
    """Verify that we find the expected version for a given requirement."""
    maya = resolver.distros["maya2020"]

    assert maya.latest_version("maya2020").name == "maya2020==2020.1"
    assert maya.latest_version("maya2020<2020.1").name == "maya2020==2020.0"


def test_config_parse(config_root, resolver, helpers):
    """Check that a config json can be parsed correctly"""
    forest = {}
    config = Config(forest, resolver)
    path = config_root / "configs" / "default" / "default.json"
    config.load(path)

    check = [
        "maya2020",
        "the_dcc_plugin_a",
        "the_dcc_plugin_b",
        "the_dcc_plugin_c",
        "houdini18.5",
        "the_dcc_plugin_d",
    ]

    # We can't do a simple comparison of Requirement keys so check that these resolved
    helpers.assert_requirements_equal(config.distros, check)

    # Check that the forest was populated correctly
    assert set(forest.keys()) == set(["default"])
    assert forest["default"] == config


def test_config_parenting(config_root, resolver):
    """Check that a correct tree structure is generated especially when loaded
    in a incorrect order.
    """

    def repr_list(node):
        return [repr(x) for x in anytree.iterators.PreOrderIter(node)]

    forest = {}
    root_paths = set((config_root,))
    # Ensure the forest has multiple trees when processing
    shared_path = config_root / "configs" / "default" / "default.json"
    Config(forest, resolver, filename=shared_path, root_paths=root_paths)

    # Load the tree structure from child to parent to test that the placeholder system
    # works as expected
    Config(
        forest,
        resolver,
        filename=config_root
        / "configs"
        / "project_a"
        / "project_a_Sc001_animation.json",
        root_paths=root_paths,
    )
    check = [
        "hab.parsers.placeholder.Placeholder('project_a')",
        "hab.parsers.placeholder.Placeholder('project_a/Sc001')",
        "hab.parsers.config.Config('project_a/Sc001/Animation')",
    ]
    assert check == repr_list(forest["project_a"])

    # Check that a middle plcaeholder was replaced
    mid_level_path = config_root / "configs" / "project_a" / "project_a_Sc001.json"
    Config(forest, resolver, filename=mid_level_path, root_paths=root_paths)
    check[1] = "hab.parsers.config.Config('project_a/Sc001')"
    assert check == repr_list(forest["project_a"])

    # Check that a middle Config object is used not replaced
    Config(
        forest,
        resolver,
        filename=config_root / "configs" / "project_a" / "project_a_Sc001_rigging.json",
        root_paths=root_paths,
    )
    check.append("hab.parsers.config.Config('project_a/Sc001/Rigging')")
    assert check == repr_list(forest["project_a"])

    # Check that a root item is replaced
    top_level_path = config_root / "configs" / "project_a" / "project_a.json"
    Config(forest, resolver, filename=top_level_path, root_paths=root_paths)
    check[0] = "hab.parsers.config.Config('project_a')"
    assert check == repr_list(forest["project_a"])

    # Verify that the correct exceptions are raised if root duplicates are loaded
    with pytest.raises(DuplicateJsonError):
        Config(forest, resolver, filename=top_level_path, root_paths=root_paths)
    assert check == repr_list(forest["project_a"])

    # and at the leaf level
    with pytest.raises(DuplicateJsonError):
        Config(forest, resolver, filename=mid_level_path, root_paths=root_paths)
    assert check == repr_list(forest["project_a"])

    # Check that the forest didn't loose the default tree
    assert ["hab.parsers.config.Config('default')"] == repr_list(forest["default"])


def test_metaclass():
    assert set(DistroVersion._properties.keys()) == set(
        [
            "alias_mods",
            "aliases",
            "distros",
            "environment",
            "environment_config",
            "filename",
            "min_verbosity",
            "name",
            "optional_distros",
            "variables",
            "version",
        ]
    )
    assert set(Config._properties.keys()) == set(
        [
            "alias_mods",
            "aliases",
            "distros",
            "environment",
            "environment_config",
            "filename",
            "min_verbosity",
            "inherits",
            "name",
            "optional_distros",
            "uri",
            "variables",
        ]
    )


class TestDump:
    def test_dump(self, resolver):
        line = "-LINE-"

        def standardize(txt):
            """Dump adds an arbitrary length border of -'s that makes str comparing
            hard. Replace it with a constant value."""
            return re.sub(r"^-+$", line, txt, flags=re.M)

        # Build the test data so we can generate the output to check
        # Note: using `repr([u"` so this test passes in python 2 and 3
        pre = ["name:  child", "uri:  not_set/child"]
        post = [
            "inherits:  True",
            "min_verbosity:  NotSet",
            "optional_distros:  NotSet",
        ]
        env = [
            "environment:  FMT_FOR_OS:  a{;}b;c:{PATH!e}{;}d",
            "              TEST:  case",
            "              UNSET_VARIABLE:  None",
        ]

        env_config = [
            "environment_config:  set:  FMT_FOR_OS:  a{;}b;c:{PATH!e}{;}d",
            "                           TEST:  case",
            "                     unset:  UNSET_VARIABLE",
        ]
        cfg = resolver.closest_config("not_set/child")
        header = f"Dump of {type(cfg).__name__}('{cfg.fullpath}')"

        # Check that both environments can be hidden
        result = cfg.dump(
            environment=False, environment_config=False, verbosity=2, color=False
        )
        check = [f"{header}\n{line}"]
        check.extend(pre)
        check.extend(post)
        check.append(line)
        check = "\n".join(check)
        assert standardize(result) == check

        # Check that both environments can be shown
        result = cfg.dump(
            environment=True, environment_config=True, verbosity=2, color=False
        )
        check = [f"{header}\n{line}"]
        check.extend(pre)
        check.extend(env)
        check.extend(env_config)
        check.extend(post)
        check.append(line)
        check = "\n".join(check)
        assert standardize(result) == check

        # Check that only environment can be shown
        result = cfg.dump(
            environment=True, environment_config=False, verbosity=2, color=False
        )
        check = [f"{header}\n{line}"]
        check.extend(pre)
        check.extend(env)
        check.extend(post)
        check.append(line)
        check = "\n".join(check)
        # Check that only environment_config can be shown
        result = cfg.dump(
            environment=False, environment_config=True, verbosity=2, color=False
        )
        check = [f"{header}\n{line}"]
        check.extend(pre)
        check.extend(env_config)
        check.extend(post)
        check.append(line)
        check = "\n".join(check)
        assert standardize(result) == check

    def test_flat(self, resolver):
        """Test additional dump settings for FlatConfig objects"""
        cfg = resolver.resolve("not_set/child")
        # Check that dump formats versions nicely
        check = re.compile(
            r"versions:  (?P<ver>aliased==2\.0, maya2020==2020\.1)"
            r"(?P<file>:  [\w:\\.\/-]+\.json)?"
        )
        # Versions are not shown with verbosity >= 1
        result = cfg.dump(color=False)
        assert not check.search(result)

        # Verbosity 2 shows just the version requirement
        result = cfg.dump(verbosity=2, color=False)
        match = check.search(result)
        assert match.group("file") is None
        assert match.group("ver") == "aliased==2.0, maya2020==2020.1"

        # Verbosity 3 also shows the json file name
        check = re.compile(
            r"versions:  (?P<vera>aliased==2\.0)(?P<filea>:  [\w:\\.\/-]+\.json)?\n"
            r"           (?P<verm>maya2020==2020\.1)(?P<filem>:  [\w:\\.\/-]+\.json)?"
        )
        result = cfg.dump(verbosity=3, color=False)
        match = check.search(result)
        assert match.group("filea") is not None
        assert match.group("filem") is not None

    @pytest.mark.parametrize("uri", ("not_set/no_distros", "not_set/empty_lists"))
    def test_no_values(self, resolver, uri):
        """If noting sets aliases or distros, don't include them in the dump text."""
        cfg = resolver.resolve(uri)

        for verbosity in range(3):
            result = cfg.dump(verbosity=verbosity, color=False)
            assert "aliases" not in result
            assert " distros:" not in result
            if not verbosity:
                # This is shown for v1 or higher
                assert "optional_distros:" not in result
            else:
                assert "optional_distros:" in result


def test_environment(resolver):
    # Check that the correct errors are raised
    cfg = resolver.closest_config("not_set/env_path_set")
    with pytest.raises(
        ValueError, match=r'You can not use PATH for the set operation: "path_variable"'
    ):
        cfg.environment

    cfg = resolver.closest_config("not_set/env_path_unset")
    with pytest.raises(ValueError, match=r"You can not unset PATH"):
        cfg.environment

    # Attempting to use a reserved env var raises an exception
    # Note: KeyError always adds quotes around the message passed so we need to
    # add them when checking the exception text
    # https://stackoverflow.com/a/24999035
    cfg = resolver.closest_config("not_set/env_path_hab_uri")
    with pytest.raises(
        KeyError, match=r"'\"HAB_URI\" is a reserved environment variable'"
    ):
        cfg.environment

    # Check environment variable resolving
    cfg = resolver.closest_config("not_set/env1")

    assert cfg.environment["APPEND_VARIABLE"] == ["append_value"]
    assert cfg.environment["MAYA_MODULE_PATH"] == ["MMP_Set"]
    assert cfg.environment["PREPEND_VARIABLE"] == ["prepend_value"]

    check = [
        "{relative_root}/prepend",
        "{relative_root}/set",
        "{relative_root}/append",
    ]
    relative_root = utils.path_forward_slash(cfg.dirname)
    check = [c.format(relative_root=relative_root) for c in check]

    assert cfg.environment["RELATIVE_VARIABLE"] == check
    assert cfg.environment["SET_RELATIVE"] == [
        "{relative_root}".format(relative_root=relative_root)
    ]
    assert cfg.environment["SET_VARIABLE"] == ["set_value"]
    assert cfg.environment["UNSET_VARIABLE"] is None
    assert cfg.environment["UNSET_VARIABLE_1"] is None

    # Check `cfg.environment is NotSet` resolves correctly
    cfg = resolver.closest_config("not_set")
    assert cfg.environment == {}

    # Ensure our tests cover the early out if the config is missing append/prepend
    cfg = resolver.closest_config("not_set/child")
    assert cfg.environment == {
        "TEST": ["case"],
        "FMT_FOR_OS": ["a{;}b;c:{PATH!e}{;}d"],
        "UNSET_VARIABLE": None,
    }


def test_flat_config(resolver):
    ret = resolver.resolve("not_set/child")
    check = {
        "TEST": ["case"],
        "FMT_FOR_OS": ["a{;}b;c:{PATH!e}{;}d"],
        "UNSET_VARIABLE": None,
        "HAB_URI": ["not_set/child"],
        "ALIASED_GLOBAL_A": ["Global A"],
        "ALIASED_GLOBAL_B": ["Global B"],
        "ALIASED_GLOBAL_C": ["Global C"],
        "ALIASED_GLOBAL_D": ["Global D"],
        "ALIASED_GLOBAL_E": None,
        "ALIASED_GLOBAL_F": ["Global F"],
    }

    assert ret.environment == check
    assert ret.environment == check
    assert ret.environment == check

    # Check for edge case where self._environment was reset if the config didn't define
    # environment, but the attached distros did.
    ret = resolver.resolve("not_set/no_env")
    assert sorted(ret.environment.keys()) == [
        "DCC_CONFIG_PATH",
        "DCC_MODULE_PATH",
        "HAB_URI",
    ]
    assert sorted(ret.environment.keys()) == [
        "DCC_CONFIG_PATH",
        "DCC_MODULE_PATH",
        "HAB_URI",
    ]


def test_flat_config_env_resolve(resolver, config_root, helpers):
    """Checks that environment variables are properly merged when resolving distros
    including inherited values. Checks that append/prepend are processed correctly
    and result in a consistent ordering of the resulting environment variables.
    """
    ret = resolver.resolve("not_set/distros")

    # Ensure the the configuration files this test relies on are configured
    # correctly. This also serves as a explanation for why the final list being
    # checked is sorted in the way it is
    raw_json = json.load(open(ret.filename))
    # The config only links to the "the_dcc" distro and no others.
    assert raw_json["distros"] == {"the_dcc": []}

    # The_dcc depends on these three distros in this order
    distro_root = config_root / "distros"
    raw_json = json.load((distro_root / "the_dcc" / "1.2" / ".hab.json").open())
    assert "the_dcc_plugin_a" in raw_json["distros"][0]
    assert "the_dcc_plugin_b" in raw_json["distros"][1]
    assert "the_dcc_plugin_e" in raw_json["distros"][2]

    # the_dcc_plugin_a depends on these two distros in this order. The dependencies
    # are resolved down the tree so "e" will show up before "b".
    distro_root = config_root / "distros"
    raw_json = json.load(
        (distro_root / "the_dcc_plugin_a" / "1.1" / ".hab.json").open()
    )
    assert "the_dcc_plugin_e" in raw_json["distros"][0]
    assert "the_dcc_plugin_d" in raw_json["distros"][1]

    # Both environment variables are appended
    for plugin in ("the_dcc_plugin_a", "the_dcc_plugin_e"):
        raw_json = json.load((distro_root / plugin / "1.1" / ".hab.json").open())
        assert "DCC_CONFIG_PATH" in raw_json["environment"]["append"]
        assert "DCC_MODULE_PATH" in raw_json["environment"]["append"]

    # One env var is appended and the other is prepended
    for plugin in ("the_dcc_plugin_b", "the_dcc_plugin_d"):
        raw_json = json.load((distro_root / plugin / "1.1" / ".hab.json").open())
        assert "DCC_CONFIG_PATH" in raw_json["environment"]["prepend"]
        assert "DCC_MODULE_PATH" in raw_json["environment"]["append"]

    # Check that the environment was actually processed depth-frist, the above
    # serves as documentation for why these env vars are ordered the way they are

    # Ensure that appends are handled correctly
    helpers.check_path_list(
        ret.environment["DCC_MODULE_PATH"],
        [
            # plugin a was first referenced so it is the first append
            str(config_root / "distros" / "the_dcc_plugin_a" / "1.1"),
            # plugin e was first in the distros specified by plugin a, so it
            # gets added next even though the_dcc referenced plugin b first
            str(config_root / "distros" / "the_dcc_plugin_e" / "1.1"),
            # plugin d was also referenced by plugin a, so it goes before plugin b
            str(config_root / "distros" / "the_dcc_plugin_d" / "1.1"),
            # Finally plugin b is added when the dependency resolver finishes
            # processing plugin a and returns to the next distro for the_dcc.
            str(config_root / "distros" / "the_dcc_plugin_b" / "1.1"),
            # plugin e was already added by plugin a, so it doesn't get re-added
            # when the dependency resolver finds it in the_dcc's distros.
        ],
    )

    # Ensure that prepends are handled correctly
    helpers.check_path_list(
        ret.environment["DCC_CONFIG_PATH"],
        [
            # plugin b is processed last, so it's prepend ends up first
            str(config_root / "distros" / "the_dcc_plugin_b" / "1.1"),
            # plugin d is processed before b, so it's prepend is next
            str(config_root / "distros" / "the_dcc_plugin_d" / "1.1"),
            # The rest are appends, and follow the same order as above
            str(config_root / "distros" / "the_dcc_plugin_a" / "1.1"),
            str(config_root / "distros" / "the_dcc_plugin_e" / "1.1"),
        ],
    )


def test_placeholder_handling(resolver):
    # We haven't defined the top level "placeholder" uri or "placeholder/undefined",
    # but we have defined "placeholder/child". Check that the Placeholder objects
    # are processed correctly. Ie in this case it inherits from the default config.
    ret = resolver.resolve("place-holder/undefined")
    # Name and context are set for every Placeholder
    assert ret.name == "place-holder"
    assert ret.context is NotSet
    assert ret.fullpath == "place-holder"

    # Verify that default configuration settings were loaded because inherits
    # defaults to True.
    assert "the_dcc" not in ret.distros.keys()
    assert "maya2020" in ret.distros.keys()
    assert "the_dcc_plugin_a" in ret.distros.keys()
    # HAB_URI is always added to the environment variables
    assert ret.environment == {"HAB_URI": ["place-holder/undefined"]}

    # Check that if inherits is False, inheritance doesn't happen with Placeholders.
    ret = resolver.resolve("place-holder/child")
    # Name and context are set for every Placeholder
    assert ret.name == "child"
    assert ret.context == ["place-holder"]
    assert ret.fullpath == "place-holder/child"

    assert "the_dcc" in ret.distros
    assert "maya2020" not in ret.distros
    assert "the_dcc_plugin_a" not in ret.distros
    assert len(ret.environment) == 3
    assert "DCC_CONFIG_PATH" in ret.environment
    assert "DCC_MODULE_PATH" in ret.environment
    # HAB_URI is always added to the environment variables
    assert "HAB_URI" in ret.environment

    # Check that if inherits is True, inheritance happens with Placeholders.
    ret = resolver.resolve("place-holder/inherits")
    # Name and context are set for every Placeholder
    assert ret.name == "inherits"
    assert ret.context == ["place-holder"]
    assert ret.fullpath == "place-holder/inherits"

    # Inherits does not define distros, so it inherits distros from default.
    assert "the_dcc" not in ret.distros.keys()
    assert "maya2020" in ret.distros.keys()
    assert "the_dcc_plugin_a" in ret.distros.keys()
    # Inherits defines environment, so its environment settings are not inherited.
    assert len(ret.environment) == 2
    assert "DCC_MODULE_PATH" not in ret.environment
    # HAB_URI is always added to the environment variables
    assert "HAB_URI" in ret.environment
    assert "TEST" in ret.environment


def test_invalid_config(config_root, resolver):
    """Check that if an invalid json file is processed, its filename is included in
    the traceback"""
    path = config_root / "invalid.json"

    # Resolve if we are using pyjson5 or the native json class
    native_json = False
    try:
        from pyjson5 import Json5Exception as _JsonException
    except ImportError:
        native_json = True
        from builtins import ValueError as _JsonException

    with pytest.raises(_JsonException) as excinfo:
        Config({}, resolver, filename=path)

    if native_json:
        # If built-in json was used, check that filename was appended to the message
        assert f'Filename("{path}")' in str(excinfo.value)
    else:
        # If pyjson5 was used, check that the filename was added to the result dict
        assert excinfo.value.result["filename"] == str(path)


def test_misc_coverage(resolver):
    """Test that cover misc lines not covered by the rest of the tests"""
    assert str(NotSet) == "NotSet"
    assert copy.copy(NotSet) is NotSet

    # Check that dirname is modified when setting a blank filename
    cfg = Config({}, resolver)
    cfg.filename = ""
    # both of these values should be set to ``Path(os.devnull)``
    assert str(cfg.filename) in ("nul", "/dev/null")
    assert str(cfg.dirname) in ("nul", "/dev/null")

    # String values are cast to the correct type
    cfg.version = "1.0"
    assert cfg.version == Version("1.0")


@pytest.mark.parametrize(
    "dirname,uri",
    (
        ("configs_parent", "not_set"),
        ("configs_child", "not_set/child"),
    ),
)
def test_duplicated_configs(config_root, resolver, dirname, uri):
    """Check that a specific config can be duplicated and that the first path
    is the used data. If there is a duplicate in the same config path, an exception
    is raised.

    The duplicates/*_1 folders have a second definition, but are in their own unique
    config_paths, so only the first found config is used.

    The duplicates/*_2 folders have a third definition. The second and third definitions
    are in the same config_path so a DuplicateJsonError is raised.
    """
    original = resolver.config_paths
    config_paths = list(original)
    # Check that config_paths raise exceptions correctly
    config_paths.insert(0, config_root / "duplicates" / f"{dirname}_1")
    resolver.config_paths = config_paths

    # Check that the first config in config_paths was used
    cfg = resolver.resolve(uri)
    assert f"{dirname}_1" in str(cfg.filename)

    # Check that an exception is raised if there are duplicate definitions from
    # the same config_paths directory.
    config_paths = list(original)
    config_paths.insert(0, config_root / "duplicates" / f"{dirname}_2")
    resolver.config_paths = config_paths
    with pytest.raises(DuplicateJsonError):
        resolver.resolve(uri)


def test_duplicated_distros(config_root, resolver):
    """Check that a specific config can be duplicated and that the first path
    is the used data. If there is a duplicate in the same config path, an exception
    is raised.

    The duplicates/distros_1 folders have a second definition, but are in their own
    unique config_paths, so only the first found config is used.

    The duplicates/distros_2 folders have a third definition. The second and third
    definitions are in the same config_path so a DuplicateJsonError is raised.
    """
    original = resolver.distro_paths

    # Check that the first config in distro_paths was used
    distro_paths = list(original)
    distro_paths.insert(0, config_root / "duplicates" / "distros_1" / "*")
    resolver.distro_paths = distro_paths

    dcc = resolver.find_distro("the_dcc==1.2")
    assert dcc.name == "the_dcc==1.2"
    assert "distros_1" in str(dcc.filename)

    # Check that an exception is raised if there are duplicate definitions from
    # the same distro_paths directory.
    distro_paths = list(original)
    distro_paths.insert(0, config_root / "duplicates" / "distros_2" / "*")
    resolver.distro_paths = distro_paths

    with pytest.raises(DuplicateJsonError):
        resolver.find_distro("the_dcc==1.2")


def test_os_specific_linux(monkeypatch, resolver):
    """Check that if "os_specific" is set to true, only env vars for the current
    os are resolved."""
    # Simulate running on a linux platform.
    monkeypatch.setattr(utils, "Platform", utils.LinuxPlatform)
    cfg = resolver.resolve("not_set/os")

    assert cfg.environment["UNSET_VARIABLE_LIN"] is None
    assert cfg.environment["SET_VARIABLE_LIN"] == ["set_value_lin"]
    assert cfg.environment["APPEND_VARIABLE_LIN"] == ["append_value_lin"]
    assert cfg.environment["PREPEND_VARIABLE_LIN"] == ["prepend_value_lin"]


def test_os_specific_win(monkeypatch, resolver):
    """Check that if "os_specific" is set to true, only env vars for the current
    os are resolved."""
    # Simulate running on a windows platform
    monkeypatch.setattr(utils, "Platform", utils.WinPlatform)
    cfg = resolver.resolve("not_set/os")

    assert cfg.environment["UNSET_VARIABLE_WIN"] is None
    assert cfg.environment["SET_VARIABLE_WIN"] == ["set_value_win"]
    assert cfg.environment["APPEND_VARIABLE_WIN"] == ["append_value_win"]
    assert cfg.environment["PREPEND_VARIABLE_WIN"] == ["prepend_value_win"]


class TestAliasMods:
    def test_global(self, resolver):
        """Check the various operations that alias_mod creates."""
        cfg = resolver.resolve("app/aliased/mod")
        alias = cfg.aliases["global"]

        # Check global hab managed env vars
        assert cfg.environment["ALIASED_GLOBAL_A"] == ["Global A"]
        assert cfg.environment["ALIASED_GLOBAL_B"] == ["Global B"]
        assert cfg.environment["ALIASED_GLOBAL_C"] == ["Global C"]
        assert cfg.environment["ALIASED_GLOBAL_D"] == ["Global D"]
        assert cfg.environment["ALIASED_GLOBAL_E"] is None
        assert cfg.environment["ALIASED_GLOBAL_F"] == ["Global F"]
        assert cfg.environment["ALIASED_MOD_GLOBAL_A"] == ["Global Mod A"]
        # This global env var was defined by the config json file.
        # Ensure that it did not get lost at some point in the process.
        assert cfg.environment["CONFIG_DEFINED"] == ["config_variable"]
        # This variable is always added by hab automatically
        assert cfg.environment["HAB_URI"] == ["app/aliased/mod"]
        # Ensure no extra env vars were defined
        assert len(cfg.environment) == 9

        # Check cmd is expected
        assert alias["cmd"][0] == "python"
        assert alias["cmd"][1].endswith("list_vars.py")

        env = alias["environment"]
        # Check that order of prepend/append env vars is correct from all sources
        # Order of processing of env vars: Global hab, alias, alias_mod.
        assert env["ALIASED_GLOBAL_A"] == [
            # 4. Prepended alias_mod env var processed last
            "Local Mod A",
            # 2. Prepend alias defined env var
            "Local A Prepend",
            # 1. Hab defined global env vars are added first
            "Global A",
            # 3. Append alias defined env var
            "Local A Append",
        ]
        # Set by alias env var(replace value)
        assert env["ALIASED_GLOBAL_C"] == ["Local C Set"]
        # This variable is unset for this alias(removing global value)
        assert env["ALIASED_GLOBAL_D"] is None
        # Set globally, and is being prepended by alias_mod
        assert env["ALIASED_GLOBAL_F"] == ["Local Mod F", "Global F"]
        # Set globally by aliased_mod, modified by aliased_mod
        assert env["ALIASED_MOD_LOCAL_B"] == ["Local Mod B"]

    def test_as_list(self, resolver):
        """Check that non-dict defined aliases are modified correctly"""
        cfg = resolver.resolve("app/aliased/mod")
        alias = cfg.aliases["global"]

        # Check cmd is expected
        assert alias["cmd"][0] == "python"
        assert alias["cmd"][1].endswith("list_vars.py")

        # Env var can be set by alias_mod without any other hab management
        assert alias["environment"]["ALIASED_MOD_LOCAL_B"] == ["Local Mod B"]

    def test_as_dict(self, resolver, config_root):
        """Additional tests for alias_mod."""
        cfg = resolver.resolve("app/aliased/mod")
        alias = cfg.aliases["as_dict"]

        # Check cmd is expected
        assert alias["cmd"][0] == "python"
        assert alias["cmd"][1].endswith("list_vars.py")

        env = alias["environment"]

        # Check alias_mod is prepended to alias defined env var
        # Also check that the alias_mods {relative_root} path is resolved to the directory
        assert (
            Path(env["ALIASED_LOCAL"][0])
            == config_root / "distros/aliased_mod/1.0/modified"
        )
        # Check that the alias {relative_root} path is resolved to it's directory
        assert Path(env["ALIASED_LOCAL"][1]) == config_root / "distros/aliased/2.0/test"
        # Env var can be set by alias_mod without any other hab management
        assert env["ALIASED_MOD_LOCAL_A"] == ["Local Mod A"]

    def test_as_dict_config(self, resolver, config_root):
        """Additional test for alias_mod being set by a config not a distro."""
        cfg = resolver.resolve("app/aliased/config")
        alias = cfg.aliases["as_dict"]
        env = alias["environment"]

        # Check alias_mod is prepended to alias defined env var and that {relative_root}
        # is pointing to the config directory
        assert Path(env["ALIASED_LOCAL"][0]) == config_root / "configs/app/config"
        # Check that the alias {relative_root} path is resolved to it's directory
        assert Path(env["ALIASED_LOCAL"][1]) == config_root / "distros/aliased/2.0/test"
        # Check that the config's alias_mod env var was added
        assert env["ALIASED_MOD_LOCAL_A"] == ["Local Config A"]

    def test_as_dict_mod_config(self, resolver, config_root):
        """Additional test for alias_mod when set by both config and distro.
        In this case the config's mods are processed before the distro mod. This
        means that the distro's changes wrap the config changes.
        """
        cfg = resolver.resolve("app/aliased/mod/config")
        alias = cfg.aliases["as_dict"]
        env = alias["environment"]

        # Check that the first alias_mod is the distro and relative to the distro
        assert (
            Path(env["ALIASED_LOCAL"][0])
            == config_root / "distros/aliased_mod/1.0/modified"
        )
        # Next is the config alias_mod and it is relative to the config
        assert Path(env["ALIASED_LOCAL"][1]) == config_root / "configs/app/config_mod"
        # Check that the alias {relative_root} path is resolved to it's directory
        assert Path(env["ALIASED_LOCAL"][2]) == config_root / "distros/aliased/2.0/test"
        # Check that the distro then config's env vars were both added in order
        assert env["ALIASED_MOD_LOCAL_A"] == ["Local Mod A", "Local Config Mod A"]


def test_duplicates(resolver):
    """Ensure consistent handling of duplicate alias names."""

    # houdini18.5 is the first distro, it's duplicate generic alias is used
    cfg = resolver.resolve("app/houdini/a")
    assert "18.5" in cfg.aliases["houdini"]["cmd"]
    assert "18.5" in cfg.aliases["houdini18.5"]["cmd"]
    assert "19.5" in cfg.aliases["houdini19.5"]["cmd"]

    # houdini19.5 is the first distro, it's duplicate generic alias is used
    cfg = resolver.resolve("app/houdini/b")
    assert "19.5" in cfg.aliases["houdini"]["cmd"]
    assert "18.5" in cfg.aliases["houdini18.5"]["cmd"]
    assert "19.5" in cfg.aliases["houdini19.5"]["cmd"]


def test_get_min_verbosity(resolver):
    cfg = resolver.resolve("verbosity")
    # Default is returned if an invalid config is passed
    assert cfg.get_min_verbosity(None, target="test", default=99) == 99
    # Default is returned if config's min_verbosity is NotSet
    data = {"min_verbosity": NotSet}
    assert cfg.get_min_verbosity(data, target="test", default=99) == 99
    # The requested target value is returned
    data["min_verbosity"] = {"global": 1, "test": 2, "hab": 3}
    assert cfg.get_min_verbosity(data, target="test", default=99) == 2
    assert cfg.get_min_verbosity(data, target="hab", default=99) == 3
    # The global value is returned if target is un-defined
    assert cfg.get_min_verbosity(data, target="missing", default=99) == 1


def test_alias_min_verbosity_default(resolver):
    """Test dumping of configs using the default target `hab`."""
    cfg = resolver.resolve("verbosity/inherit")

    with utils.verbosity_filter(resolver, verbosity=None):
        result = cfg.aliases
        assert sorted(result.keys()) == ["vb0", "vb1", "vb2", "vb3", "vb_default"]

    with utils.verbosity_filter(resolver, verbosity=2):
        result = cfg.aliases
        assert sorted(result.keys()) == ["vb0", "vb1", "vb2", "vb_default"]

    with utils.verbosity_filter(resolver, verbosity=1):
        result = cfg.aliases
        assert sorted(result.keys()) == ["vb0", "vb1", "vb_default"]

    with utils.verbosity_filter(resolver, verbosity=0):
        result = cfg.aliases
        assert sorted(result.keys()) == ["vb0", "vb_default"]


def test_alias_min_verbosity_hab_gui(resolver):
    """Test dumping of aliases using the non-default target `hab-gui`.."""
    cfg = resolver.resolve("verbosity/inherit")

    with utils.verbosity_filter(resolver, verbosity=None, target="hab-gui"):
        result = cfg.aliases
        assert sorted(result.keys()) == ["vb0", "vb1", "vb2", "vb3", "vb_default"]

    with utils.verbosity_filter(resolver, verbosity=2, target="hab-gui"):
        result = cfg.aliases
        assert sorted(result.keys()) == ["vb1", "vb2", "vb3", "vb_default"]

    with utils.verbosity_filter(resolver, verbosity=1, target="hab-gui"):
        result = cfg.aliases
        assert sorted(result.keys()) == ["vb2", "vb3", "vb_default"]

    with utils.verbosity_filter(resolver, verbosity=0, target="hab-gui"):
        result = cfg.aliases
        assert sorted(result.keys()) == ["vb3", "vb_default"]


def test_update_environ(resolver):
    pathsep = utils.Platform.pathsep(utils.Platform.default_ext())
    cfg = resolver.resolve("app/aliased/mod")

    # Pre-existing env var values. These are not managed by hab persist
    inherited = {
        "IGNORED": "This variable not managed by hab and is ignored",
    }

    # The global env vars that the hab config manages.
    check_global = {
        "ALIASED_GLOBAL_A": "Global A",
        "ALIASED_GLOBAL_B": "Global B",
        "ALIASED_GLOBAL_C": "Global C",
        "ALIASED_GLOBAL_D": "Global D",
        "ALIASED_GLOBAL_F": "Global F",
        "ALIASED_MOD_GLOBAL_A": "Global Mod A",
        "CONFIG_DEFINED": "config_variable",
        "HAB_URI": "app/aliased/mod",
    }
    # Include the inherited values
    check_global.update(inherited)

    def new_dict():
        return dict(inherited)

    def check_freeze(env):
        # Ensure the HAB_FREEZE variable was actually set on env and remove
        # it to make checking the rest of the dict easier.
        freeze = env.pop("HAB_FREEZE")
        # Check that it starts with the version identifier.
        assert re.match(r"v\d*:.+", freeze)

    # Check that global env vars were added
    env = new_dict()
    cfg.update_environ(env)
    check_freeze(env)
    assert env == check_global

    # And that variables are removed that are set to unset
    env = {"ALIASED_GLOBAL_E": "To be removed"}
    env.update(inherited)
    cfg.update_environ(env)
    check_freeze(env)
    assert env == check_global

    # Check aliased env vars are passed excluding global hab env vars
    # Alias defines no env vars
    env = new_dict()
    cfg.update_environ(env, alias_name="as_str", include_global=False)
    assert env == inherited

    # Alias output checking
    check_alias = {
        "ALIASED_GLOBAL_A": pathsep.join(
            ["Local Mod A", "Local A Prepend", "Global A", "Local A Append"]
        ),
        "ALIASED_GLOBAL_C": "Local C Set",
        "ALIASED_GLOBAL_F": pathsep.join(["Local Mod F", "Global F"]),
        "ALIASED_MOD_LOCAL_B": "Local Mod B",
    }
    # Include the inherited values
    check_alias.update(inherited)

    # Alias "global" defines several env vars, these include hab global env vars.
    env = new_dict()
    cfg.update_environ(env, alias_name="global", include_global=False)
    assert env == check_alias

    # Check aliased env vars are passed including global hab env vars
    env = new_dict()
    cfg.update_environ(env, alias_name="as_str", include_global=True)
    check_freeze(env)
    assert env == check_global

    # Check aliased env vars are passed including global hab env vars
    env = new_dict()
    cfg.update_environ(env, alias_name="global", include_global=True)
    check = dict(check_global, **check_alias)
    # This env var is un-set by the alias
    del check["ALIASED_GLOBAL_D"]
    check_freeze(env)
    assert env == check


class TestCustomVariables:
    def test_distro(self, uncached_resolver):
        """Test that a distro processes valid custom variables correctly."""
        distro = uncached_resolver.distros["maya2024"].latest_version("maya2024")
        assert distro.name == "maya2024==2024.0"

        # Check that the custom variables are assigned
        check = {
            "maya_root_linux": "/usr/autodesk/maya2024/bin",
            "maya_root_windows": "C:/Program Files/Autodesk/Maya2024/bin",
        }
        assert distro.variables == check

        # Check that the aliases have not had their custom vars replaced
        alias = distro.aliases["windows"][0]
        assert alias[0] == "maya"
        assert alias[1]["cmd"] == "{maya_root_windows}/maya.exe"
        alias = distro.aliases["linux"][0]
        assert alias[0] == "maya"
        assert alias[1]["cmd"] == "{maya_root_linux}/maya"

        # Check that the custom variables are replaced when formatting
        formatted = distro.format_environment_value(distro.aliases)

        alias = formatted["windows"][0]
        assert alias[0] == "maya"
        assert alias[1]["cmd"] == f"{check['maya_root_windows']}/maya.exe"
        alias = formatted["linux"][0]
        assert alias[0] == "maya"
        assert alias[1]["cmd"] == f"{check['maya_root_linux']}/maya"

    @pytest.mark.parametrize("config_class", ("Config", "FlatConfig"))
    def test_config(self, uncached_resolver, config_class):
        """Test that a config processes valid custom variables correctly."""
        if config_class == "Config":
            cfg = uncached_resolver.closest_config("project_a")
            assert type(cfg) == Config
        else:
            cfg = uncached_resolver.resolve("project_a")
            assert type(cfg) == FlatConfig

        check = {
            "mount_linux": "/blur/g",
            "mount_windows": "G:",
        }
        assert cfg.variables == check

        cfg.environment
        env = cfg.frozen_data["environment"]
        # Check the mount_linux variable was replaced correctly
        assert env["linux"]["HOUDINI_OTLSCAN_PATH"] == [
            "/blur/g/project_a/cfg/hdas",
            "/blur/g/_shared/cfg/hdas",
            "&",
        ]
        assert env["linux"]["OCIO"] == ["/blur/g/project_a/cfg/ocio/v0001/config.ocio"]

        # Check the mount_windows variable was replaced correctly
        assert env["windows"]["HOUDINI_OTLSCAN_PATH"] == [
            "G:/project_a/cfg/hdas",
            "G:/_shared/cfg/hdas",
            "&",
        ]
        assert env["windows"]["OCIO"] == ["G:/project_a/cfg/ocio/v0001/config.ocio"]

    @pytest.mark.parametrize(
        "variables,invalid",
        (
            ({"relative_root": "Not Valid"}, "relative_root"),
            ({"relative_root": "Not Valid", ";": "Not Valid"}, ";, relative_root"),
            ({"valid": "Valid", ";": "Not Valid"}, ";"),
        ),
    )
    def test_reserved(self, uncached_resolver, variables, invalid, tmpdir):
        """Test that using a reserved variable raises an exception."""

        # Create a test distro file using the given reserved variables
        template = {
            "name": "maya2024",
            "version": "2024.99",
            "variables": variables,
        }
        distro_file = tmpdir / "maya2024" / ".hab.json"
        Path(distro_file).parent.mkdir()
        with distro_file.open("w") as fle:
            json.dump(template, fle, indent=4, cls=utils.HabJsonEncoder)

        # Add the test distro to hab's distro search. We don't need to call
        # `clear_caches` because distros haven't been resolved yet.
        uncached_resolver.distro_paths.append(Path(tmpdir))

        # When distros are resolved, an exception should be raised
        with pytest.raises(
            ReservedVariableNameError,
            match=rf"'{invalid}' are reserved variable name\(s\) for hab",
        ):
            uncached_resolver.distros
