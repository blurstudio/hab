import anytree
from habitat.parsers import Application, Config
import json
import os
from packaging.version import Version
import pytest
from tabulate import tabulate


def test_application_parse(config_root):
    """Check that a application json can be parsed correctly"""
    app = Application()
    path = os.path.join(
        config_root, "distros", "all_settings", "0.1.0.dev1", ".habitat.json"
    )
    app.load(path)

    check = json.load(open(path))

    assert check["name"] == app.name
    assert Version(check["version"]) == app.version
    assert check["environment"] == app.environment_config
    assert check["requires"] == app.requires
    assert check["aliases"] == app.aliases


def test_config_parse(config_root):
    """Check that a config json can be parsed correctly"""
    forest = {}
    config = Config(forest)
    path = os.path.join(config_root, "configs", "default", "default.json")
    config.load(path)

    check = json.load(open(path))

    assert check["name"] == config.name
    assert check["context"] == config.context
    assert check["inherits"] == config.inherits
    assert check["apps"] == config.apps
    assert check["requires"] == config.requires

    # Check that the forest was populated correctly
    assert set(forest.keys()) == set(["default"])
    assert forest["default"] == config


def test_config_parenting(config_root):
    """Check that a correct tree structure is generated especially when loaded
    in a incorrect order.
    """

    def repr_list(node):
        return [repr(x) for x in anytree.iterators.PreOrderIter(node)]

    forest = {}
    # Ensure the forest has multiple trees when processing
    shared_path = os.path.join(config_root, "configs", "default", "default.json")
    Config(forest, filename=shared_path)

    # Load the tree structure from child to parent to test that the placeholder system
    # works as expected
    Config(
        forest,
        filename=os.path.join(
            config_root, "configs", "project_a", "project_a_Sc001_animation.json"
        ),
    )
    check = [
        "habitat.parsers.Placeholder(:project_a)",
        "habitat.parsers.Placeholder(:project_a:Sc001)",
        "habitat.parsers.Config(:project_a:Sc001:Animation)",
    ]
    assert check == repr_list(forest["project_a"])

    # Check that a middle plcaeholder was replaced
    mid_level_path = os.path.join(
        config_root, "configs", "project_a", "project_a_Sc001.json"
    )
    Config(forest, filename=mid_level_path)
    check[1] = "habitat.parsers.Config(:project_a:Sc001)"
    assert check == repr_list(forest["project_a"])

    # Check that a middle Config object is used not replaced
    Config(
        forest,
        filename=os.path.join(
            config_root, "configs", "project_a", "project_a_Sc001_rigging.json"
        ),
    )
    check.append("habitat.parsers.Config(:project_a:Sc001:Rigging)")
    assert check == repr_list(forest["project_a"])

    # Check that a root item is replaced
    top_level_path = os.path.join(config_root, "configs", "project_a", "project_a.json")
    Config(forest, filename=top_level_path)
    check[0] = "habitat.parsers.Config(:project_a)"
    assert check == repr_list(forest["project_a"])

    # Verify that the correct exceptions are raised if root duplicates are loaded
    with pytest.raises(ValueError):
        Config(forest, filename=top_level_path)
    assert check == repr_list(forest["project_a"])

    # and at the leaf level
    with pytest.raises(ValueError):
        Config(forest, filename=mid_level_path)
    assert check == repr_list(forest["project_a"])

    # Check that the forest didn't loose the default tree
    assert ["habitat.parsers.Config(:default)"] == repr_list(forest["default"])


def test_metaclass():
    assert Application._properties == set(
        ["name", "environment_config", "requires", "aliases"]
    )
    assert Config._properties == set(
        ["name", "environment_config", "requires", "inherits", "apps"]
    )


def test_dump(resolver):
    # Build the test data so we can generate the output to check
    # Note: using `repr([u"` so this test passes in python 2 and 3
    pre = [["apps", "<NotSet>"]]
    post = [
        ["inherits", "True"],
        ["name", "child"],
        ["requires", repr([u"tikal"])],
    ]
    env = [["environment", repr({u"TEST": u"case"})]]
    env_config = [["environment_config", repr({u"set": {u"TEST": u"case"}})]]
    cfg = resolver.closest_config(":not_set:child")

    # Check that both environments can be hidden
    result = cfg.dump(environment=False, environment_config=False)
    assert result == tabulate(pre + post)

    # Check that both environments can be shown
    result = cfg.dump(environment=True, environment_config=True)
    assert result == tabulate(pre + env + env_config + post)

    # Check that only environment can be shown
    result = cfg.dump(environment=True, environment_config=False)
    assert result == tabulate(pre + env + post)

    # Check that only environment_config can be shown
    result = cfg.dump(environment=False, environment_config=True)
    assert result == tabulate(pre + env_config + post)


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
    ] == "{dot}/prepend;{dot}/set;{dot}/append".format(dot=cfg.dirname)
    assert cfg.environment["SET_RELATIVE"] == "{dot}".format(dot=cfg.dirname)
    assert cfg.environment["SET_VARIABLE"] == "set_value"
    assert cfg.environment["UNSET_VARIABLE"] == ""
    assert cfg.environment["UNSET_VARIABLE_1"] == ""

    # Check `cfg.environment is NotSet` resolves correctly
    cfg = resolver.closest_config(":not_set")
    assert cfg.environment == {}

    # Ensure our tests cover the early out if the config is missing append/prepend
    cfg = resolver.closest_config(":not_set:child")
    assert cfg.environment == {"TEST": "case"}
