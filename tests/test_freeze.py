import os
from pathlib import PurePosixPath, PureWindowsPath

import pytest

from hab import NotSet, Resolver, Site, utils
from hab.parsers import UnfrozenConfig


def update_config(check, config_root, platform):
    """Correctly fill in {config_root} for the given frozen config.
    This allows the test to pass no matter what os it is run on.

    Args:
        check (dict): A frozen config loaded from a test json file.
        config_root (pathlib.Path): The config_root string format variable is
            replaced with this value if it matches platform. Otherwise the generic
            "c:\\" for windows and "/hab" for linux is used.
        platform (str): The current platform the test is running on.
    """
    env = check["environment"]
    for plat in env:
        if plat == platform:
            cfg_root = config_root
        else:
            cfg_root = "c:" if plat == "windows" else "/hab"
        for k, values in env[plat].items():
            for i, v in enumerate(values):
                env[plat][k][i] = v.format(config_root=cfg_root)


def test_json_dumps():
    """Check that dumps_json returns the expected results for non-standard
    objects."""
    data = {"NotSet": NotSet}
    assert utils.dumps_json(data) == '{"NotSet": null}'
    assert utils.dumps_json(data, indent=2) == "\n".join(
        [
            "{",
            '  "NotSet": null',
            "}",
        ]
    )


@pytest.mark.parametrize("platform,pathsep", (("win32", ";"), ("linux", ":")))
def test_freeze(monkeypatch, config_root, platform, pathsep):
    monkeypatch.setattr(utils, "Platform", utils.WinPlatform)
    monkeypatch.setattr(os, "pathsep", pathsep)
    site = Site([config_root / "site_main.json"])
    resolver = Resolver(site=site)
    cfg_root = utils.path_forward_slash(config_root)

    # Add a platform_path_maps mapping to convert the current hab checkout path
    # to a generic know path on the other platform for uniform testing.
    mappings = site.frozen_data[site.platform]["platform_path_maps"]
    mappings["local-hab"] = {
        "linux": PurePosixPath("/hab"),
        "windows": PureWindowsPath("c:/"),
    }
    # Preserve the current platform's path so it matches the frozen output
    if site.platform == "windows":
        mappings["local-hab"]["windows"] = PureWindowsPath(cfg_root)
    else:
        mappings["local-hab"][site.platform] = PurePosixPath(cfg_root)

    # Resolve the URI for frozen testing
    cfg = resolver.resolve("not_set/distros")

    for alias in ("dcc", "dcc1.2"):
        # Ensure consistent testing across platforms. cfg has the current os's
        # file paths instead of what is stored in frozen.json
        cfg.frozen_data["aliases"]["linux"][alias]["cmd"] = "TEST_DIR_NAME//the_dcc"
        cfg.frozen_data["aliases"]["windows"][alias][
            "cmd"
        ] = "TEST_DIR_NAME\\the_dcc.exe"

        # For ease of testing we also need to convert the distro tuple to a list
        # that way it matches the json data stored in frozen.json
        as_list = list(cfg.frozen_data["aliases"]["linux"][alias]["distro"])
        cfg.frozen_data["aliases"]["linux"][alias]["distro"] = as_list
        as_list = list(cfg.frozen_data["aliases"]["windows"][alias]["distro"])
        cfg.frozen_data["aliases"]["windows"][alias]["distro"] = as_list

    # Ensure the HAB_URI environment variable is defined on the FlatConfig object
    # When checking the return from `cfg.freeze()` below HAB_URI is removed to
    # simplify the output json data.
    assert cfg.frozen_data["environment"]["linux"]["HAB_URI"] == ["not_set/distros"]
    assert cfg.frozen_data["environment"]["windows"]["HAB_URI"] == ["not_set/distros"]

    ret = cfg.freeze()
    check_file = config_root / "frozen.json"
    check = utils.json.load(check_file.open())
    # Apply template values so we can easily check against frozen.
    update_config(check, cfg_root, site.platform)

    assert ret == check

    # Check that optional properties are excluded from the dictionary if empty
    ret = cfg.freeze()
    assert "versions" in ret
    # Simulate having versions being empty
    cfg.frozen_data["versions"] = []
    ret = cfg.freeze()
    assert "versions" not in ret

    # Frozen configs don't need to encode alias_mods, the modifications are
    # already baked into aliases
    assert "alias_mods" not in ret


def test_unfreeze(config_root, resolver):
    check_file = config_root / "frozen.json"

    # Note: For this test, we don't need to worry about "{config_root}" templates.
    frozen_config = utils.json.load(check_file.open())
    cfg = UnfrozenConfig(frozen_config, resolver)

    assert cfg.context == frozen_config["context"]
    assert cfg.name == frozen_config["name"]
    assert cfg.uri == frozen_config["uri"]
    assert (
        cfg.frozen_data["aliases"]["linux"]["dcc"]
        == frozen_config["aliases"]["linux"]["dcc"]
    )
    assert (
        cfg.frozen_data["aliases"]["windows"]["dcc"]
        == frozen_config["aliases"]["windows"]["dcc"]
    )

    assert cfg.versions == frozen_config["versions"]

    # HAB_URI is removed from the frozen data. Storing it per platform would
    # just make the frozen string longer. Re-add these to the check data so it
    # matches UnfrozenConfig also adding it.
    frozen_config["environment"]["linux"]["HAB_URI"] = "not_set/distros"
    frozen_config["environment"]["windows"]["HAB_URI"] = "not_set/distros"
    # Check that environment was restored correctly
    assert cfg.frozen_data["environment"] == frozen_config["environment"]

    # Check various class overrides
    assert cfg._dump_versions(cfg.versions) == sorted(frozen_config["versions"])
    assert cfg.aliases == frozen_config["aliases"][utils.Platform.name()]
    assert "dcc" in cfg.aliases
    assert cfg.fullpath == "not_set/distros"
    assert cfg.inherits is False

    # Frozen configs don't need to encode alias_mods, the modifications are
    # already baked into aliases
    assert cfg.alias_mods is NotSet

    # Check passing a string to UnfrozenConfig instead of a dict
    check_file = config_root / "frozen_no_distros.json"
    checks = utils.json.load(check_file.open())
    v2 = checks["version2"]
    cfg = UnfrozenConfig(v2, resolver)

    # The HAB_URI env var is included in the frozen config on a UnfrozenConfig
    check = checks["raw"]
    check["environment"]["linux"]["HAB_URI"] = check["uri"]
    check["environment"]["windows"]["HAB_URI"] = check["uri"]
    assert cfg.frozen_data == check


def test_decode_freeze(config_root):
    check_file = config_root / "frozen_no_distros.json"
    checks = utils.json.load(check_file.open())
    v1 = checks["version1"]
    raw = checks["raw"]

    # Check that supported freeze's are decoded correctly
    assert utils.decode_freeze(v1) == raw
    assert utils.decode_freeze(checks["version2"]) == raw

    # Check that padded versions are also supported
    assert utils.decode_freeze(f"v01:{v1[3:]}") == raw

    # Check that non-versioned freeze strings raise an helpful exception
    for check in (
        # Missing `v1:`
        v1[3:],
        # Missing `v'
        f"1:{v1[3:]}",
    ):
        with pytest.raises(
            ValueError, match=r"Missing freeze version information in format `v0:...`"
        ):
            utils.decode_freeze(check)

    # Check that versions other than numbers raise a helpful exception
    with pytest.raises(ValueError, match=r"Version INVALID is not valid."):
        utils.decode_freeze(f"vINVALID:{v1[3:]}")

    # check that other version encodings return nothing
    assert utils.decode_freeze(f"v3:{v1[3:]}") is None
    assert utils.decode_freeze(f"v0:{v1[3:]}") is None


def test_encode_freeze(config_root, resolver):
    cfg = resolver.resolve("not_set/no_distros")
    check_file = config_root / "frozen_no_distros.json"
    checks = utils.json.load(check_file.open())

    # Check that the dict contains the expected contents
    freeze = cfg.freeze()
    assert freeze == checks["raw"]

    # Check that supported version encodings are correct
    version1 = utils.encode_freeze(freeze, version=1)
    assert version1 == checks["version1"]
    version2 = utils.encode_freeze(freeze, version=2)
    assert version2 == checks["version2"]

    # Check that if a version is not defined, the default(2) is used.
    # This is used if `Site.get("freeze_version")` is not defined.
    version_none = utils.encode_freeze(freeze, version=None)
    assert version_none == checks["version2"]

    # Check that other version encodings return nothing
    assert utils.encode_freeze(freeze, version=0) is None
    assert utils.encode_freeze(freeze, version=3) is None

    # Check that site kwarg is respected
    site = Site()
    # Force the site to version 1, but version is not specified
    site["freeze_version"] = 1
    version1 = utils.encode_freeze(freeze, version=None, site=site)
    assert version1 == checks["version1"]

    # If version is passed, site is ignored
    version1 = utils.encode_freeze(freeze, version=2, site=site)
    assert version1 == checks["version2"]


def test_resolver_freeze_configs(tmpdir, config_root, uncached_resolver, helpers):
    """Test `Resolver.freeze_configs`.

    This method generates the frozen config for all non-placeholder URI's hab
    finds. This makes it fairly easy to diff bulk config changes as json.

    It checks the output against `tests/resolver_freeze_configs.json`. For testing
    simplicity, this file has had its aliases and environment sections removed.
    """
    result = uncached_resolver.freeze_configs()
    # Simplify the test by removing dynamic data containing paths. Other tests
    # verify that a specific URI can be frozen successfully. This test verifies
    # that freeze_configs generates a consistent output for all URI's.
    for data in result.values():
        if isinstance(data, str):
            continue
        if "aliases" in data:
            del data["aliases"]
        if "environment" in data:
            del data["environment"]

    check_file = config_root / "resolver_freeze_configs.json"
    result_file = tmpdir / "result.json"
    with result_file.open("w") as fle:
        txt = utils.dumps_json(result, indent=4)
        fle.write(txt)
    helpers.compare_files(result_file, check_file)
