from collections import OrderedDict

import pytest
from packaging.requirements import Requirement

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
