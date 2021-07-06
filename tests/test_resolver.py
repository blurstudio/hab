import anytree
from habitat import Resolver
from habitat.parsers import NotSet
import os
import pytest


def test_environment_variables(config_root):
    """Check that Resolver's init respects the environment variables it uses."""
    config_paths_env = ["a/config/path", "b/config/path"]
    distro_paths_env = ["a/distro/path", "b/distro/path"]
    config_paths_direct = ["z/config/path", "zz/config/path"]
    distro_paths_direct = ["z/distro/path", "zz/distro/path"]

    # backup the environment variables so we can restore them
    old_environ = dict(os.environ)
    # Set the config environment variables
    os.environ["HAB_CONFIG_PATHS"] = os.pathsep.join(config_paths_env)
    os.environ["HAB_DISTRO_PATHS"] = os.pathsep.join(distro_paths_env)

    try:
        # configured by the environment
        resolver_env = Resolver()
        # configured by passed arguments
        resolver_direct = Resolver(
            config_paths=config_paths_direct, distro_paths=distro_paths_direct
        )
    finally:
        # Restore the original environment variables
        os.environ.clear()
        os.environ.update(old_environ)

    # Check the environment configured resolver
    assert resolver_env.config_paths == config_paths_env
    assert resolver_env.distro_paths == distro_paths_env

    # Check the directly configured resolver
    assert resolver_direct.config_paths == config_paths_direct
    assert resolver_direct.distro_paths == distro_paths_direct


def test_config(resolver):
    """Spot check a few of the parsed configs to enesure config works."""
    any_resolver = anytree.Resolver()
    default = resolver.configs["default"]
    assert default.name == "default"
    assert any_resolver.get(default, ":default:Sc1").name == "Sc1"
    assert any_resolver.get(default, ":default:Sc11").name == "Sc11"


@pytest.mark.parametrize(
    "path,result,reason",
    (
        (":project_a", ":project_a", "Complete root path not found"),
        (":project_a:Sc001", ":project_a:Sc001", "Complete secondary path not found"),
        (
            ":project_a:Sc001:Animation",
            ":project_a:Sc001:Animation",
            "Complete tertiary path not found",
        ),
        (
            ":project_a:Sc001:Modeling",
            ":project_a:Sc001",
            "Invalid tertiary path not fallen back",
        ),
        (
            ":project_a:Sc999:Modeling",
            ":project_a",
            "Invalid secondary path not fallen back",
        ),
        (
            ":project_a:very:many:paths:resolved",
            ":project_a",
            "Invalid n-length path not fallen back",
        ),
        # Default fallback
        (":project_z", ":default", "Default root not returned for invalid root."),
        (
            ":project_z:Sc001",
            ":default",
            "Default root not returned if no matching secondary.",
        ),
        (":project_z:Sc101", ":default:Sc1", "Default secondary not returned"),
        (
            ":project_z:Sc110",
            ":default:Sc11",
            "More specific default secondary not returned",
        ),
    ),
)
def test_closest_config(resolver, path, result, reason):
    """Test that closest_config returns the expected results."""
    assert resolver.closest_config(path).fullpath == result, reason


def test_reduced(resolver):
    """Check that NotSet is used if no value is provided."""
    cfg = resolver.closest_config(":not_set")
    assert cfg.apps == {"maya2020": []}
    assert cfg.environment == NotSet
    assert cfg.requires == NotSet
    assert cfg.inherits is False
    assert cfg.name == "not_set"

    cfg = resolver.closest_config(":not_set:child")
    # Not set on the child so should be NotSet(ie doesn't inherit from parent)
    assert cfg.apps == NotSet
    # Settings defined on the child
    assert cfg.environment == {u"set": {u"TEST": u"case"}}
    assert cfg.requires == ["tikal"]
    assert cfg.inherits is True
    assert cfg.name == "child"

    # Verify that a flattened config properly inherits values
    reduced = cfg.reduced(resolver)
    # Inherited from the parent
    assert reduced.apps == {"maya2020": []}
    # Values defind on the child are preserved
    assert reduced.environment == {u"set": {u"TEST": u"case"}}
    assert reduced.requires == ["tikal"]
    assert reduced.inherits is True
    assert reduced.name == "child"
