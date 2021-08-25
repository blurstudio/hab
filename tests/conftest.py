from habitat import Resolver
from contextlib import contextmanager
import os
import pytest


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
