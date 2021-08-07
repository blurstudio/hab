import anytree
from habitat.parsers import ApplicationVersion, Config, NotSet
import json
import os
from packaging.version import Version
import pytest
import re
import sys
from tabulate import tabulate


def test_application_parse(config_root, resolver):
    """Check that a application json can be parsed correctly"""
    forest = {}
    app = ApplicationVersion(forest, resolver)
    path = os.path.join(
        config_root, "distros", "all_settings", "0.1.0.dev1", ".habitat.json"
    )
    app.load(path)
    check = json.load(open(path))

    assert "{name}=={version}".format(**check) == app.name
    assert Version(check["version"]) == app.version
    assert check["environment"] == app.environment_config

    assert check["aliases"] == app.aliases
    assert ["all_settings"] == app.context

    # Verify that if the json file doesn't have "version" defined it uses the
    # parent directory as its version.
    app = ApplicationVersion(forest, resolver)
    path = os.path.join(config_root, "distros", "maya", "2020.0", ".habitat.json")
    app.load(path)
    check = json.load(open(path))

    # tests\distros\maya\2020.0\.habitat.json does not have "version"
    # defined. This allows us to test that ApplicationVersion will pull the
    # version number from the parent directory not the json file.
    assert "version" not in check
    assert app.version == Version("2020.0")


def test_application_version(resolver):
    """Verify that we find the expected version for a given requirement."""
    maya = resolver.distros["maya2020"]

    assert maya.latest_version("maya2020").name == "maya2020==2020.1"
    assert maya.latest_version("maya2020<2020.1").name == "maya2020==2020.0"


def test_config_parse(config_root, resolver):
    """Check that a config json can be parsed correctly"""
    forest = {}
    config = Config(forest, resolver)
    path = os.path.join(config_root, "configs", "default", "default.json")
    config.load(path)

    check = json.load(open(path))

    assert check["name"] == config.name
    assert check["context"] == config.context
    assert check["inherits"] == config.inherits

    # We can't do a simple comparison of Requirement keys so check that these resolved
    assert len(check["distros"]) == len(config.distros)
    for k in config.distros:
        assert k.name in check["distros"]
        assert check["distros"][k.name] == config.distros[k]

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
    # Ensure the forest has multiple trees when processing
    shared_path = os.path.join(config_root, "configs", "default", "default.json")
    Config(forest, resolver, filename=shared_path)

    # Load the tree structure from child to parent to test that the placeholder system
    # works as expected
    Config(
        forest,
        resolver,
        filename=os.path.join(
            config_root, "configs", "project_a", "project_a_Sc001_animation.json"
        ),
    )
    check = [
        "habitat.parsers.Placeholder(':project_a')",
        "habitat.parsers.Placeholder(':project_a:Sc001')",
        "habitat.parsers.Config(':project_a:Sc001:Animation')",
    ]
    assert check == repr_list(forest["project_a"])

    # Check that a middle plcaeholder was replaced
    mid_level_path = os.path.join(
        config_root, "configs", "project_a", "project_a_Sc001.json"
    )
    Config(forest, resolver, filename=mid_level_path)
    check[1] = "habitat.parsers.Config(':project_a:Sc001')"
    assert check == repr_list(forest["project_a"])

    # Check that a middle Config object is used not replaced
    Config(
        forest,
        resolver,
        filename=os.path.join(
            config_root, "configs", "project_a", "project_a_Sc001_rigging.json"
        ),
    )
    check.append("habitat.parsers.Config(':project_a:Sc001:Rigging')")
    assert check == repr_list(forest["project_a"])

    # Check that a root item is replaced
    top_level_path = os.path.join(config_root, "configs", "project_a", "project_a.json")
    Config(forest, resolver, filename=top_level_path)
    check[0] = "habitat.parsers.Config(':project_a')"
    assert check == repr_list(forest["project_a"])

    # Verify that the correct exceptions are raised if root duplicates are loaded
    with pytest.raises(ValueError):
        Config(forest, resolver, filename=top_level_path)
    assert check == repr_list(forest["project_a"])

    # and at the leaf level
    with pytest.raises(ValueError):
        Config(forest, resolver, filename=mid_level_path)
    assert check == repr_list(forest["project_a"])

    # Check that the forest didn't loose the default tree
    assert ["habitat.parsers.Config(':default')"] == repr_list(forest["default"])


def test_metaclass():
    assert ApplicationVersion._properties == set(
        ["name", "environment_config", "requires", "aliases", "distros", "version"]
    )
    assert Config._properties == set(
        ["name", "environment_config", "requires", "inherits", "distros", "uri"]
    )


def test_dump(resolver):
    # Build the test data so we can generate the output to check
    # Note: using `repr([u"` so this test passes in python 2 and 3
    pre = [["distros", "<NotSet>"]]
    post = [
        ["inherits", "True"],
        ["name", "child"],
        ["requires", []],
        ["uri", ":not_set:child"],
    ]
    env = [["environment", "TEST: case"], ["", "UNSET_VARIABLE:"]]
    if sys.version_info[0] == 2:
        check = "{u'set': {u'TEST': u'case'}, u'unset': [u'UNSET_VARIABLE']}"
    else:
        check = "{'set': {'TEST': 'case'}, 'unset': ['UNSET_VARIABLE']}"

    env_config = [["environment_config", check]]
    cfg = resolver.closest_config(":not_set:child")
    header = "Dump of {}('{}')\n{{}}".format(type(cfg).__name__, cfg.fullpath)

    # Check that both environments can be hidden
    result = cfg.dump(environment=False, environment_config=False)
    assert result == header.format(tabulate(pre + post))

    # Check that both environments can be shown
    result = cfg.dump(environment=True, environment_config=True)
    assert result == header.format(tabulate(pre + env + env_config + post))

    # Check that only environment can be shown
    result = cfg.dump(environment=True, environment_config=False)
    assert result == header.format(tabulate(pre + env + post))

    # Check that only environment_config can be shown
    result = cfg.dump(environment=False, environment_config=True)
    assert result == header.format(tabulate(pre + env_config + post))


def test_dump_flat(resolver):
    """Test additional dump settings for FlatConfig objects"""
    cfg = resolver.resolve(":not_set:child")
    # Check that dump formats versions nicely
    result = cfg.dump()
    check = "versions     {!r}".format([u"maya2020==2020.1"])
    assert check in result


def test_environment(resolver):
    # Check that the correct errors are raised
    cfg = resolver.closest_config(":not_set:env_path_set")
    with pytest.raises(ValueError) as excinfo:
        cfg.environment
    assert (
        str(excinfo.value)
        == 'You can not use PATH for the set operation: "path_variable"'
    )

    cfg = resolver.closest_config(":not_set:env_path_unset")
    with pytest.raises(ValueError) as excinfo:
        cfg.environment
    assert str(excinfo.value) == "You can not unset PATH"

    # Check environment variable resolving
    cfg = resolver.closest_config(":not_set:env1")

    assert cfg.environment["APPEND_VARIABLE"] == "append_value"
    assert cfg.environment["MAYA_MODULE_PATH"] == "MMP_Set"
    assert cfg.environment["PREPEND_VARIABLE"] == "prepend_value"
    assert cfg.environment[
        "RELATIVE_VARIABLE"
    ] == "{dot}/prepend{pathsep}{dot}/set{pathsep}{dot}/append".format(
        dot=cfg.dirname, pathsep=os.path.pathsep
    )
    assert cfg.environment["SET_RELATIVE"] == "{dot}".format(dot=cfg.dirname)
    assert cfg.environment["SET_VARIABLE"] == "set_value"
    assert cfg.environment["UNSET_VARIABLE"] == ""
    assert cfg.environment["UNSET_VARIABLE_1"] == ""

    # Check `cfg.environment is NotSet` resolves correctly
    cfg = resolver.closest_config(":not_set")
    assert cfg.environment == {}

    # Ensure our tests cover the early out if the config is missing append/prepend
    cfg = resolver.closest_config(":not_set:child")
    assert cfg.environment == {"TEST": "case", u"UNSET_VARIABLE": ""}


def test_flat_config(resolver):
    ret = resolver.resolve(":not_set:child")
    assert ret.environment == {"TEST": "case", u"UNSET_VARIABLE": ""}
    assert ret.environment == {"TEST": "case", u"UNSET_VARIABLE": ""}
    assert ret.environment == {"TEST": "case", u"UNSET_VARIABLE": ""}

    # Check for edge case where self._environment was reset if the config didn't define
    # environment, but the attached distros did.
    ret = resolver.resolve(":not_set:no_env")
    assert list(ret.environment.keys()) == ["DCC_MODULE_PATH"]
    assert list(ret.environment.keys()) == ["DCC_MODULE_PATH"]


def test_invalid_config(config_root, resolver):
    """Check that if an invalid json file is processed, its filename is included in
    the traceback"""
    path = os.path.join(config_root, "invalid.json")
    check = re.escape(r' Filename: "{}"'.format(path))

    with pytest.raises(ValueError, match=check):
        Config({}, resolver, filename=path)


def test_misc_coverage(resolver):
    """Test that cover misc lines not covered by the rest of the tests"""
    assert str(NotSet) == "NotSet"

    # Check that dirname is modified when setting a blank filename
    cfg = Config({}, resolver)
    cfg.filename = ""
    assert cfg.filename == ""
    assert cfg.dirname == ""

    # String values are cast to the correct type
    cfg.version = "1.0"
    assert cfg.version == Version("1.0")


def test_write_script_bat(resolver, tmpdir):
    cfg = resolver.resolve(":not_set:child")
    file_config = tmpdir.join("config.bat")
    file_launch = tmpdir.join("launch.bat")
    cfg.write_script(str(file_config), str(file_launch))

    assert 'cmd.exe /k "{}"\n'.format(file_config) == open(str(file_launch)).read()

    config = open(str(file_config)).read()
    assert 'set "PROMPT=[:not_set:child] $P$G"' in config
    assert 'set "TEST=case"' in config
    assert r'doskey maya="C:\Program Files\Autodesk\Maya2020\bin\maya.exe" $*' in config


def test_write_script_ps1(resolver, tmpdir):
    cfg = resolver.resolve(":not_set:child")
    file_config = tmpdir.join("config.ps1")
    file_launch = tmpdir.join("launch.ps1")
    cfg.write_script(str(file_config), str(file_launch))

    assert (
        'powershell.exe -NoExit -ExecutionPolicy Unrestricted . "{}"\n'.format(
            file_config
        )
        == open(str(file_launch)).read()
    )

    config = open(str(file_config)).read()
    assert "function PROMPT {'[:not_set:child] ' + $(Get-Location) + '>'}" in config
    assert '$env:TEST = "case"' in config
    assert (
        r"function maya() { C:\Program` Files\Autodesk\Maya2020\bin\maya.exe $args }"
        in config
    )


def test_write_script_sh(resolver, tmpdir):
    cfg = resolver.resolve(":not_set:child")
    file_config = tmpdir.join("config")
    file_launch = tmpdir.join("launch")
    cfg.write_script(str(file_config), str(file_launch))

    # assert (
    #     'powershell.exe -NoExit -ExecutionPolicy Unrestricted . "{}"\n'.format(
    #         file_config
    #     )
    #     == open(str(file_launch)).read()
    # )

    # config = open(str(file_config)).read()
    # assert "function PROMPT {'[:not_set:child] ' + $(Get-Location) + '>'}" in config
    # assert '$env:TEST = "case"' in config
    # assert (
    #     r"function maya() { C:\Program` Files\Autodesk\Maya2020\bin\maya.exe $args }"
    #     in config
    # )
