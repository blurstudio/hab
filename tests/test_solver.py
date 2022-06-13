import pytest
from hab.solvers import Solver
from packaging.requirements import Requirement


@pytest.mark.parametrize(
    "value,check",
    (
        # List and tuple inputs
        (['the_dcc'], ['the_dcc']),
        (('the_dcc', 'a_dcc'), ['the_dcc', 'a_dcc']),
        (['the_dcc', 'a_dcc'], ['the_dcc', 'a_dcc']),
        ([Requirement('the_dcc'), 'a_dcc'], ['the_dcc', 'a_dcc']),
        # simple dict inputs
        ({'the_dcc': None, 'b_dcc': None}, ['the_dcc', 'b_dcc']),
        ({'the_dcc': 'c_dcc'}, ['the_dcc', 'c_dcc']),
        ({Requirement('a_dcc'): None}, ['a_dcc']),
        ({'a_dcc': Requirement('a_dcc')}, ['a_dcc']),
        ({Requirement('the_dcc'): Requirement('a_dcc')}, ['the_dcc', 'a_dcc']),
        # Merging requirements
        ({'the_dcc': 'the_dcc>=1.0', 'b_dcc': None}, ['the_dcc>=1.0', 'b_dcc']),
        ({'the_dcc>=0.9': 'the_dcc>=1.0'}, ['the_dcc>=0.9,>=1.0']),
        # Dict containing lists
        (
            {'the_dcc': ['a_dcc', 'b_dcc'], 'an_dcc': ['a_dcc', 'c_dcc']},
            ['the_dcc', 'an_dcc', 'a_dcc', 'b_dcc', 'c_dcc'],
        ),
    ),
)
def test_simplify_requirements(helpers, value, check):
    ret = Solver.simplify_requirements(value)
    helpers.assert_requirements_equal(ret, check)
