import anytree
from habitat.parsers import Application, Config
import json
import os
from packaging.version import Version
import pytest


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
    assert check["environment"] == app.environment
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
