import logging
import sys
from collections import OrderedDict

import pytest
from packaging.requirements import Requirement

from hab import utils
from hab.errors import InvalidRequirementError, MaxRedirectError
from hab.solvers import Solver


@pytest.mark.parametrize(
    "value,check",
    (
        # List and tuple inputs
        (["the_dcc"], ["the_dcc"]),
        (("the_dcc", "a_dcc"), ["the_dcc", "a_dcc"]),
        (["the_dcc", "a_dcc"], ["the_dcc", "a_dcc"]),
        ([Requirement("the_dcc"), "a_dcc"], ["the_dcc", "a_dcc"]),
        # simple dict inputs
        ({"the_dcc": None, "b_dcc": None}, ["the_dcc", "b_dcc"]),
        ({"the_dcc": "c_dcc"}, ["the_dcc", "c_dcc"]),
        ({Requirement("a_dcc"): None}, ["a_dcc"]),
        ({"a_dcc": Requirement("a_dcc")}, ["a_dcc"]),
        ({Requirement("the_dcc"): Requirement("a_dcc")}, ["the_dcc", "a_dcc"]),
        # Merging requirements
        ({"the_dcc": "the_dcc>=1.0", "b_dcc": None}, ["the_dcc>=1.0", "b_dcc"]),
        ({"the_dcc>=0.9": "the_dcc>=1.0"}, ["the_dcc>=0.9,>=1.0"]),
        # Dict containing lists
        (
            {"the_dcc": ["a_dcc", "b_dcc"], "an_dcc": ["a_dcc", "c_dcc"]},
            ["the_dcc", "an_dcc", "a_dcc", "b_dcc", "c_dcc"],
        ),
    ),
)
def test_simplify_requirements(helpers, value, check):
    ret = Solver.simplify_requirements(value)
    helpers.assert_requirements_equal(ret, check)


@pytest.mark.parametrize(
    "requirements,match",
    (
        (
            {"no_existant_distro": Requirement("no_existant_distro")},
            "Unable to find a distro for requirement: no_existant_distro",
        ),
        # Testing marker output. Using Invalid so this test works on all platforms
        (
            {"no_exist": Requirement("no_exist;platform_system!='Invalid'")},
            'Unable to find a distro for requirement: no_exist; platform_system != "Invalid"',
        ),
        (
            {"the_dcc": Requirement("the_dcc==0.0.0")},
            r'Unable to find a valid version for "the_dcc==0.0.0" in versions \[.+\]',
        ),
        (
            # This requirement is not possible because the_dcc_plugin_b requires the_dcc<1.2
            {
                "the_dcc": Requirement("the_dcc>1.1"),
                "the_dcc_plugin_b": Requirement("the_dcc_plugin_b<1.0"),
            },
            r'Unable to find a valid version for "the_dcc<1.2,>1.1" in versions \[.+\]',
        ),
        pytest.param(
            {"the_dcc": Requirement("the_dcc==1.0,==2.0")},
            'Specifier for "the_dcc" excludes all possible versions: "==1.0,==2.0"',
            marks=pytest.mark.skipif(
                sys.version_info < (3, 8),
                reason="Library does not support python version",
            ),
        ),
    ),
)
def test_invalid_requirement_errors(uncached_resolver, requirements, match):
    """Test that the correct error is raised if an invalid or missing requirement
    is specified."""
    with pytest.raises(InvalidRequirementError, match=match):
        uncached_resolver.resolve_requirements(requirements)


def test_solver_errors(uncached_resolver):
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

    solver = Solver(requirements, uncached_resolver)
    solver.max_redirects = 0
    with pytest.raises(MaxRedirectError, match="Redirect limit of 0 reached"):
        solver.resolve()


def test_omittable(caplog, uncached_resolver):
    """Test the solver respects the `omittable` property. This will prevent raising
    an error if a distro is required but is not found.
    """
    # A set of requirements that includes distros that hab can't find
    requirements = OrderedDict(
        (
            ("the_dcc", Requirement("the_dcc")),
            ("the_dcc_plugin_b", Requirement("the_dcc_plugin_b==0.9")),
            ("missing_distro", Requirement("missing_distro")),
            ("missing_distro_b", Requirement("missing_distro_b==1.0")),
        )
    )
    # By default this should raise an InvalidRequirementError
    solver = Solver(requirements, uncached_resolver)
    with pytest.raises(InvalidRequirementError, match="requirement: missing_distro"):
        solver.resolve()

    # However if that distro is marked as omittable, then a warning is logged
    # and no exception is raised.
    omittable = ["the_dcc_plugin_b", "missing_distro", "missing_distro_b"]
    solver = Solver(requirements, uncached_resolver, omittable=omittable)
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        reqs = solver.resolve()
    # This plugin can be found so it is not skipped
    assert "the_dcc_plugin_b" not in caplog.text
    # These plugins don't exist and will be skipped by the omittable setting.
    assert "Skipping missing omitted requirement: missing_distro" in caplog.text
    assert "Skipping missing omitted requirement: missing_distro_b==1.0" in caplog.text
    check = [
        "the_dcc",
        "the_dcc_plugin_a",
        "the_dcc_plugin_b",
        "the_dcc_plugin_d",
        "the_dcc_plugin_e",
    ]
    assert sorted(reqs.keys()) == check


@pytest.mark.parametrize(
    "specifier,limit,result,limit_valid",
    (
        ("==1.0,==1.0", None, True, True),
        ("==1.0,==1.1", None, False, True),
        ("==1.0,!=1.1", None, True, True),
        ("==1.0,!=1.0", None, False, True),
        (">=1.2,<1.2.a1", None, False, True),
        (">=1.2,<1.3.a1", None, True, True),
        ("~=1.2", None, True, True),
        ("~=1.2", "==1.2", True, True),
        ("~=1.2", "==1.3,==1.0", False, False),
    ),
)
def test_specifier_valid(specifier, limit, result, limit_valid, caplog):
    """Test utils.specifier_valid. In python 3.7 and lower it always returns True"""
    if sys.version_info < (3, 8):
        assert utils.specifier_valid(specifier, limit=limit)
    else:
        caplog.clear()
        caplog.set_level(logging.DEBUG)
        assert utils.specifier_valid(specifier, limit=limit) is result
        # Verify that limit was processed if specified
        if limit:
            assert f"Applying specifier limit: {limit}" in caplog.text
            # If the limit is invalid, a warning is logged
            if not limit_valid:
                assert f"Specifier limit is invalid: {limit}" in caplog.text
                # This should always result in a false return
                assert result is False
