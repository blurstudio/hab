import pytest
from colorama import Fore

from hab.parsers.format_parser import FormatParser

# Short access to the required colorama color codes for formatting
cg = Fore.GREEN
cr = Fore.RESET
cy = Fore.YELLOW


@pytest.mark.parametrize(
    "uri,pre,color,zero,one",
    (
        # Top level URI placeholder is not indented
        ("app", "", False, "app", "app"),
        ("app", "", True, f"{cg}app{cr}", f"{cg}app{cr}"),
        # Child URI is defined, The URI is not turned green and is indented
        ("app/aliased", "  ", False, "  app/aliased", '  app/aliased: "{filename}"'),
        (
            "app/aliased",
            "  ",
            True,
            "  app/aliased",
            f'  app/aliased: {cy}"{{filename}}"{cr}',
        ),
        # Grand-child URI is defined, The URI is not turned green and is indented
        (
            "app/aliased/mod",
            "  ",
            False,
            "  app/aliased/mod",
            '  app/aliased/mod: "{filename}"',
        ),
        (
            "app/aliased/mod",
            "  ",
            True,
            "  app/aliased/mod",
            f'  app/aliased/mod: {cy}"{{filename}}"{cr}',
        ),
        # Top level URI is defined so not a placeholder (not indented)
        ("project_a", "", False, "project_a", 'project_a: "{filename}"'),
        (
            "project_a",
            "",
            True,
            f"{cg}project_a{cr}",
            f'{cg}project_a{cr}: {cy}"{{filename}}"{cr}',
        ),
        # Parent and child URI is not defined, The URI is not turned green and no filename
        ("app/houdini", "  ", False, "  app/houdini", "  app/houdini"),
        (
            "app/houdini",
            "  ",
            True,
            "  app/houdini",
            "  app/houdini",
        ),
    ),
)
def test_format_parser_uri(config_root, uncached_resolver, uri, pre, color, zero, one):
    """Test various uses of `hab.parsers.format_parser.FormatParser`."""
    cfg = uncached_resolver.closest_config(uri)

    # Test verbosity set to zero
    formatter = FormatParser(0, color=color)
    result = formatter.format(cfg, "uri", pre)
    assert result == zero

    # Test verbosity of one
    formatter = FormatParser(1, color=color)
    result = formatter.format(cfg, "uri", pre)
    assert result == one.format(filename=cfg.filename)


def test_dump_forest_callable(uncached_resolver, config_root):
    """Check that Resolver.dump_forest handles passing a callable to fmt."""
    formatter = FormatParser(1, color=False)
    result = []
    for line in uncached_resolver.dump_forest(
        uncached_resolver.distros, attr="name", fmt=formatter.format, truncate=3
    ):
        result.append(line)

    result = "\n".join(result)

    check = [
        "aliased",
        f'''  aliased==2.0: "{config_root / 'distros/aliased/2.0/.hab.json'}"''',
        "aliased_mod",
        f'''  aliased_mod==1.0: "{config_root / 'distros/aliased_mod/1.0/.hab.json'}"''',
        "aliased_verbosity",
        f"  aliased_verbosity==1.0: "
        f'''"{config_root / 'distros/aliased_verbosity/1.0/.hab.json'}"''',
    ]
    check = "\n".join(check)
    assert result.startswith(check)
