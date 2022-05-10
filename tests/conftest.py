import os
import pytest

from contextlib import contextmanager
from habitat import Resolver
from packaging.requirements import Requirement


@pytest.fixture
def config_root():
    return os.path.dirname(__file__)


@pytest.fixture
def resolver(config_root):
    """Return a standard testing resolver"""
    config_paths = (os.path.join(config_root, "configs", "*"),)
    distro_paths = (os.path.join(config_root, "distros", "*"),)
    return Resolver(config_paths=config_paths, distro_paths=distro_paths)


class Helpers(object):
    """A collection of reusable functions that tests can use."""

    @staticmethod
    def assert_requirements_equal(req, check):
        """Assert that a requirement dict matches a list of requirements.

        Args:
            req (dict): A Requirement dictionary matching the output of
                ``habitat.solvers.Solvers.simplify_requirements``.
            check (list): A list of requirement strings. This takes a list
                so writing tests requires less boilerplate.

        Raises:
            AssertionError: If the provided req and check don't exactly match.
        """
        assert len(req) == len(check)
        for chk in check:
            chk = Requirement(chk)
            assert Helpers.cmp_requirement(req[chk.name], chk)

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
