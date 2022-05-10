import anytree
import os
import pytest

from collections import OrderedDict
from packaging.requirements import Requirement

from habitat import Resolver
from habitat.errors import MaxRedirectError
from habitat.parsers import NotSet
from habitat.solvers import Solver


def test_environment_variables(config_root, helpers):
    """Check that Resolver's init respects the environment variables it uses."""
    config_paths_env = ["a/config/path", "b/config/path"]
    distro_paths_env = ["a/distro/path", "b/distro/path"]
    config_paths_direct = ["z/config/path", "zz/config/path"]
    distro_paths_direct = ["z/distro/path", "zz/distro/path"]

    # backup the environment variables so we can restore them
    with helpers.reset_environ():
        # Set the config environment variables
        os.environ["HAB_CONFIG_PATHS"] = os.pathsep.join(config_paths_env)
        os.environ["HAB_DISTRO_PATHS"] = os.pathsep.join(distro_paths_env)

        # configured by the environment
        resolver_env = Resolver()
        # configured by passed arguments
        resolver_direct = Resolver(
            config_paths=config_paths_direct, distro_paths=distro_paths_direct
        )

    # Check the environment configured resolver
    assert resolver_env.config_paths == config_paths_env
    assert resolver_env.distro_paths == distro_paths_env

    # Check the directly configured resolver
    assert resolver_direct.config_paths == config_paths_direct
    assert resolver_direct.distro_paths == distro_paths_direct

    # Check that we properly split string paths into a lists if provided
    resolver_env = Resolver(
        config_paths=os.pathsep.join(config_paths_env),
        distro_paths=os.pathsep.join(distro_paths_env),
    )
    assert resolver_env.config_paths == config_paths_env
    assert resolver_env.distro_paths == distro_paths_env


def test_config(resolver):
    """Spot check a few of the parsed configs to enesure config works."""
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
    ),
)
def test_closest_config(resolver, path, result, reason):
    """Test that closest_config returns the expected results."""
    assert resolver.closest_config(path).fullpath == result, reason


def test_dump_forest(resolver):
    """Test the dump_forest method on resolver"""
    result = resolver.dump_forest(resolver.configs)
    check = "\n".join(
        (
            "default",
            "    habitat.parsers.Config('default')",
            "    |-- habitat.parsers.Config('default/Sc1')",
            "    +-- habitat.parsers.Config('default/Sc11')",
            "not_set",
            "    habitat.parsers.Config('not_set')",
            "    |-- habitat.parsers.Config('not_set/child')",
            "    |-- habitat.parsers.Config('not_set/env1')",
            "    |-- habitat.parsers.Config('not_set/env_path_set')",
            "    |-- habitat.parsers.Config('not_set/env_path_unset')",
            "    |-- habitat.parsers.Config('not_set/distros')",
            "    +-- habitat.parsers.Config('not_set/no_env')",
            "project_a",
            "    habitat.parsers.Config('project_a')",
            "    +-- habitat.parsers.Config('project_a/Sc001')",
            "        |-- habitat.parsers.Config('project_a/Sc001/Animation')",
            "        +-- habitat.parsers.Config('project_a/Sc001/Rigging')",
        )
    )
    assert result == check


def test_reduced(resolver, helpers):
    """Check that NotSet is used if no value is provided."""
    cfg = resolver.closest_config("not_set")
    check = ["maya2020"]
    helpers.assert_requirements_equal(cfg.distros, check)
    assert cfg.environment_config == NotSet
    assert cfg.inherits is False
    assert cfg.name == "not_set"

    cfg = resolver.closest_config("not_set/child")
    # Not set on the child so should be NotSet(ie doesn't inherit from parent)
    assert cfg.distros == NotSet
    # Settings defined on the child
    assert cfg.environment_config == {
        u"set": {u"TEST": u"case"},
        u"unset": [u"UNSET_VARIABLE"],
    }
    assert cfg.inherits is True
    assert cfg.name == "child"

    # Verify that a flattened config properly inherits values
    reduced = cfg.reduced(resolver)
    # Inherited from the parent
    helpers.assert_requirements_equal(reduced.distros, check)
    # Values defined on the child are preserved
    assert reduced.environment_config == {
        u"set": {u"TEST": u"case"},
        u"unset": [u"UNSET_VARIABLE"],
    }
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


def test_solver_errors(resolver):
    """Test that the correct errors are raised"""

    # Check that if we exceed max_redirects a MaxRedirectError is raised
    # Note: To have a stable test, the order of requirements matters. So this needs to
    # use a list or OrderedDict to guarantee that the_dcc==1.2 requirements are
    # processed before the_dcc_plugin_b which specifies the_dcc<1.2 forcing a redirect.
    requirements = OrderedDict(
        (
            ("the_dcc", Requirement("the_dcc")),
            ("the_dcc_plugin_b", Requirement("the_dcc_plugin_b==0.9")),
        )
    )

    solver = Solver(requirements, resolver)
    solver.max_redirects = 0
    with pytest.raises(MaxRedirectError):
        solver.resolve()


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


def test_resolve_requirements_errors(resolver):

    # This requirement is not possible because the_dcc_plugin_b requires the_dcc<1.2
    requirements = {
        Requirement("the_dcc>1.1"): None,
        Requirement("the_dcc_plugin_b<1.0"): None,
    }

    # TODO: Use a custom exception not Exception
    with pytest.raises(Exception):
        resolver.resolve_requirements(requirements)
