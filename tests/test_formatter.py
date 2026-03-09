import os

import pytest

from hab import utils
from hab.formatter import ExpandMode, Formatter
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

    # Check that "!e" uses the env var value if `expand=ExpandMode.ToShell` not
    # the shell specifier.
    assert (
        Formatter(language, expand=ExpandMode.ToShell).format(fmt, regular_var="V")
        == expanded
    )

    # Coverage of the __str__ method of ExpandMode
    assert str(ExpandMode.Preserve) == "Preserve"
    assert str(ExpandMode.ToShell) == "ToShell"
    assert str(ExpandMode.Remove) == "Remove"


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


def test_invalid(monkeypatch):
    """Verify the expected behavior for given formatter input."""
    assert "INVALID" not in os.environ
    fmt_s = "-{INVALID}-"
    fmt_e = "-{INVALID!e}-"

    # Not using !s so it raises an error if not in os.environ or passed
    for expand in ExpandMode:
        with pytest.raises(KeyError, match=r"INVALID"):
            Formatter("sh", expand=expand).format(fmt_s)

    # If the value is passed it resolves correctly
    for expand in ExpandMode:
        fmtr = Formatter("sh", expand=expand)
        check = "-AS-KWARG-"
        assert fmtr.format(fmt_s, INVALID="AS-KWARG") == check
        assert fmtr.format(fmt_e, INVALID="AS-KWARG") == check

    # When not using !e, env vars are ignored
    monkeypatch.setenv("INVALID", "NOW-VALID")
    with pytest.raises(KeyError, match=r"INVALID"):
        Formatter("sh").format(fmt_s)

    # When using !e the env var is converted to shell expansion variable
    # when using the default ExpandMode.Preserve
    assert Formatter("sh").format(fmt_e) == "-$INVALID-"
    assert Formatter("shwin").format(fmt_e) == "-$INVALID-"
    assert Formatter("batch").format(fmt_e) == "-%INVALID%-"
    assert Formatter("ps").format(fmt_e) == "-$env:INVALID-"

    # When using ExpandMode.Remove or ToShell it replaces the variable
    assert Formatter("sh", expand=ExpandMode.ToShell).format(fmt_e) == "-NOW-VALID-"
    assert Formatter("sh", expand=ExpandMode.Remove).format(fmt_e) == "-NOW-VALID-"
