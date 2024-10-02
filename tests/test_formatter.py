import pytest

from hab import utils
from hab.formatter import Formatter
from hab.parsers import Config


@pytest.mark.parametrize(
    "language,expanded,not_expanded",
    (
        ("sh", "_V_a-var_:_$INVALID_", "_V_$VALID_:_$INVALID_"),
        # Bash formatting is different on windows for env vars
        ("shwin", "_V_a-var_:_$INVALID_", "_V_$VALID_:_$INVALID_"),
        ("ps", "_V_a-var_;_$env:INVALID_", "_V_$env:VALID_;_$env:INVALID_"),
        ("batch", "_V_a-var_;_%INVALID%_", "_V_%VALID%_;_%INVALID%_"),
        (None, "_V_a-var_{;}_{INVALID!e}_", "_V_{VALID!e}_{;}_{INVALID!e}_"),
    ),
)
def test_env_format(language, expanded, not_expanded, monkeypatch):
    """Check that the custom Formatter class works as expected.

    This check tests:
        - You can still use pass kwargs like a normal Formatter.
        - ``!e`` is converted for set env vars if ``expand==True``.
          ``VALID`` becomes ``a-var``.
        - ``!e`` uses the shell env specifier for set env vars if ``expand==False``.
          (``VALID`` becomes ``$VALID`` for bash.)
        - ``!e`` uses the shell env specifier for unset env variables.
          (``INVALID`` becomes ``$INVALID`` for bash.)
        - ``{;}`` gets converted to the shell's ``:`` or ``;``.
    """
    monkeypatch.setenv("VALID", "a-var")
    monkeypatch.delenv("INVALID", raising=False)

    fmt = "_{regular_var}_{VALID!e}_{;}_{INVALID!e}_"

    # Check that "!e" is converted to the correct shell specific specifier.
    assert Formatter(language).format(fmt, regular_var="V") == not_expanded

    # Check that "!e" uses the env var value if `expand=True` not the shell specifier.
    assert Formatter(language, expand=True).format(fmt, regular_var="V") == expanded


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
