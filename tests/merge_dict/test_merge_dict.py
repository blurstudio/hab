import json

import pytest

from hab import utils
from hab.merge_dict import MergeDict


@pytest.mark.parametrize(
    "filename,platforms",
    (
        # if os_specific is not set, add the variables to all platforms
        ("os_agnostic.json", None),
        # If platform is specified, only the requested platforms are returned
        ("os_agnostic_platforms.json", ("reactos",)),
        # os_specific is set, so merge "*" with each platform
        ("os_specific.json", None),
        # if os_specific is set to False, treat it the same as os_agnostic
        ("os_specific_false.json", None),
        # If platform is specified in an os_specific context, only the requested
        # platforms are returned
        ("os_specific_platforms.json", ("reactos",)),
    ),
)
def test_apply_platform_wildcards(config_root, resolver, filename, platforms):
    """Test merging of "*" os specific dicts into platform specific dictionaries"""
    json_path = config_root / "merge_dict" / filename

    with json_path.open() as fle:
        test_data = json.load(fle)

    # The data to feed the apply_platform_wildcards method
    in_data = test_data["in_data"]
    # The output from the apply_platform_wildcards method to check against
    out_data = test_data["out_data"]

    kwargs = {}
    if platforms is not None:
        kwargs["platforms"] = platforms
        kwargs["site"] = resolver.site

    merger = MergeDict(**kwargs)
    result = merger.apply_platform_wildcards(in_data)

    assert result == out_data


def test_path_split(monkeypatch):
    # Check the pathsep argument is respected
    assert utils.Platform.path_split("a:b", pathsep=":") == ["a", "b"]
    assert utils.Platform.path_split("a;b", pathsep=";") == ["a", "b"]
    assert utils.Platform.path_split("a-b", pathsep="-") == ["a", "b"]

    # Check if pathsep argument is not passed, the current os is respected
    # Windows
    monkeypatch.setattr(utils, "Platform", utils.WinPlatform)
    assert utils.Platform.path_split("a;b") == ["a", "b"]
    assert utils.Platform.path_split("a:b") == ["a:b"]
    # Linux/OSX
    monkeypatch.setattr(utils, "Platform", utils.LinuxPlatform)
    assert utils.Platform.path_split("a;b") == ["a;b"]
    assert utils.Platform.path_split("a:b") == ["a", "b"]

    # If a single windows file path is passed on linux/osx it's not split on ":"
    assert utils.Platform.path_split(r"Z:\test", pathsep=":") == [r"Z:\test"]
    # TODO: This test covers the current behavior but ideally we can figure out
    # a way to prevent splitting the two windows file paths.
    assert utils.Platform.path_split(r"Z:\test:X:test", pathsep=":") == [
        "Z",
        r"\test",
        "X",
        "test",
    ]


@pytest.mark.parametrize("filename", ("merge_agnostic.json", "merge_specific.json"))
def test_merge(config_root, filename):
    """Test that we can merge multiple "*" dicts into a single dict."""
    json_path = config_root / "merge_dict" / filename

    with json_path.open() as fle:
        test_data = json.load(fle)

    # The data to feed the apply_platform_wildcards method
    file_one = test_data["file_one"]
    file_two = test_data["file_two"]
    # The output from the apply_platform_wildcards method to check against
    out_data = test_data["out_data"]

    merger = MergeDict()
    result = merger.apply_platform_wildcards(file_one)
    result = merger.apply_platform_wildcards(file_two, output=result)

    assert result == out_data
