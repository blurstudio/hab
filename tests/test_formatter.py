from hab import utils
from hab.formatter import Formatter
from hab.parsers import Config


def test_e_format():
    assert Formatter("sh").format("-{PATH!e}-") == "-$PATH-"
    assert Formatter("sh").format("-{;}-") == "-:-"
    # Bash formatting is different on windows for env vars
    assert Formatter("shwin").format("-{PATH!e}-") == "-$PATH-"
    assert Formatter("shwin").format("-{;}-") == "-:-"

    assert Formatter("ps").format("-{PATH!e}-") == "-$env:PATH-"
    assert Formatter("ps").format("-{;}-") == "-;-"

    assert Formatter("batch").format("-{PATH!e}-") == "-%PATH%-"
    assert Formatter("batch").format("-{;}-") == "-;-"

    assert Formatter(None).format("-{PATH!e}-") == "-{PATH!e}-"
    assert Formatter(None).format("-{;}-") == "-{;}-"


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


def test_format_environment_value(resolver):
    forest = {}
    config = Config(forest, resolver)

    # test_format_environment_value doesn't replace the special formatters.
    # This allows us to delay these formats to only when creating the final
    # shell scripts, not the first time we evaluate environment variables.
    value = "a{;}b;c:{PATH!e}{;}d"
    assert config.format_environment_value(value, ext=None) == value
