import os

import pytest

from hab import utils
from hab.formatter import Formatter
from hab.parsers import Config


@pytest.mark.parametrize(
    "language,shell,pathsep",
    (
        ("sh", "-$PATH-", "-:-"),
        # Bash formatting is different on windows for env vars
        ("shwin", "-$PATH-", "-:-"),
        ("ps", "-$env:PATH-", "-;-"),
        ("batch", "-%PATH%-", "-;-"),
        (None, "-{PATH!e}-", "-{;}-"),
    ),
)
def test_e_format(language, shell, pathsep):
    """Check that "{VAR_NAME!e}" is properly formatted."""
    path = os.environ["PATH"]

    # Check that "!e" is converted to the correct shell specific specifier.
    assert Formatter(language).format("-{PATH!e}-") == shell

    # Check that "!e" uses the env var value if `expand=True` not the shell specifier.
    assert Formatter(language, expand=True).format("-{PATH!e}-") == f"-{path}-"

    # Check that the pathsep variable `{;}` is converted to the correct value
    assert Formatter(language).format("-{;}-") == pathsep


def test_language_from_ext(monkeypatch):
    # Arbitrary values are not modified
    assert Formatter.language_from_ext(".abc") == ".abc"
    assert Formatter.language_from_ext("anything") == "anything"

    # Test that known file exts are translated to the shell name
    assert Formatter.language_from_ext(".bat") == "batch"
    assert Formatter.language_from_ext(".cmd") == "batch"
    assert Formatter.language_from_ext(".ps1") == "ps"

    # Bash formatting is different on windows for env vars
    with monkeypatch.context() as m:
        m.setattr(utils, "Platform", utils.WinPlatform)
        assert Formatter.language_from_ext(".sh") == "shwin"
        assert Formatter.language_from_ext("") == "shwin"

        m.setattr(utils, "Platform", utils.LinuxPlatform)
        assert Formatter.language_from_ext(".sh") == "sh"
        assert Formatter.language_from_ext("") == "sh"


def test_format_environment_value(uncached_resolver):
    forest = {}
    config = Config(forest, uncached_resolver)

    # test_format_environment_value doesn't replace the special formatters.
    # This allows us to delay these formats to only when creating the final
    # shell scripts, not the first time we evaluate environment variables.
    value = "a{;}b;c:{PATH!e}{;}d"
    assert config.format_environment_value(value, ext=None) == value
