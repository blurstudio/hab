import os
from contextlib import contextmanager
from pathlib import Path, PurePath

import pytest
from packaging.requirements import Requirement

from hab import Resolver, Site


@pytest.fixture
def config_root():
    return Path(__file__).parent


@pytest.fixture
def resolver(config_root):
    """Return a standard testing resolver"""
    site = Site([config_root / "site_main.json"])
    return Resolver(site=site)


class Helpers(object):
    """A collection of reusable functions that tests can use."""

    @staticmethod
    def assert_requirements_equal(req, check):
        """Assert that a requirement dict matches a list of requirements.

        Args:
            req (dict): A Requirement dictionary matching the output of
                ``hab.solvers.Solvers.simplify_requirements``.
            check (list): A list of requirement strings. This takes a list
                so writing tests requires less boilerplate.

        Raises:
            AssertionError: If the provided req and check don't exactly match.
        """
        try:
            assert len(req) == len(check)
        except AssertionError:
            # Provide additional information to help debug a failing test. The simple
            # len assert doesn't make it easy to debug a failing test
            print(" Requirement dict ".center(50, "-"))
            print(req)
            print(" Check ".center(50, "-"))
            print(check)
            raise
        for chk in check:
            chk = Requirement(chk)
            assert Helpers.cmp_requirement(req[chk.name], chk)

    @staticmethod
    def check_path_list(paths, checks):
        """Casts the objects in both lists to PurePath objects so they can be
        reliably asserted and differences easily viewed in the pytest output.
        """
        paths = [PurePath(p) for p in paths]
        checks = [PurePath(p) for p in checks]
        assert paths == checks

    @staticmethod
    def cmp_requirement(a, b):
        """Convenience method to check if two Requirement objects are the same.

        Args:
            a (Requirement): The first Requirement to compare
            b (Requirement): The second Requirement to compare

        Returns:
            bool: If a and b represent the same requirement
        """
        return type(a) == type(b) and str(a) == str(b)

    @staticmethod
    @contextmanager
    def reset_environ():
        """Resets the environment variables once the with context exits."""
        old_environ = dict(os.environ)
        try:
            yield
        finally:
            # Restore the original environment variables
            os.environ.clear()
            os.environ.update(old_environ)


@pytest.fixture
def helpers():
    """Expose the Helpers class as a fixture for ease of use in tests."""
    return Helpers
