import os
import sys
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
    env = check['environment']
    for plat in env:
        if plat == platform:
            cfg_root = config_root
        else:
            cfg_root = 'c:' if plat == 'windows' else '/hab'
        for k, values in env[plat].items():
            for i, v in enumerate(values):
                env[plat][k][i] = v.format(config_root=cfg_root)


def test_json_dumps():
    """Check that dumps_json returns the expected results for non-standard
    objects."""
    data = {"NotSet": NotSet}
    assert utils.dumps_json(data) == '{"NotSet": null}'
    assert utils.dumps_json(data, indent=2) == '\n'.join(
        [
            '{',
            '  "NotSet": null',
            '}',
        ]
    )


@pytest.mark.parametrize("platform,pathsep", (("win32", ";"), ("linux", ":")))
def test_freeze(monkeypatch, config_root, platform, pathsep):
    monkeypatch.setattr(sys, 'platform', platform)
    monkeypatch.setattr(os, 'pathsep', pathsep)
    site = Site([config_root / "site_main.json"])
    resolver = Resolver(site=site)

    cfg_root = utils.path_forward_slash(config_root)
    cfg = resolver.resolve("not_set/distros")

    # Add a platform_path_maps mapping to convert the current hab checkout path
    # to a generic know path on the other platform for uniform testing.
    mappings = site.frozen_data[site.platform]["platform_path_maps"]
    mappings['local-hab'] = {
        "linux": PurePosixPath("/hab"),
        "windows": PureWindowsPath("c:/"),
    }
    # Preserve the current platform's path so it matches the frozen output
    if site.platform == "windows":
        mappings['local-hab']['windows'] = PureWindowsPath(cfg_root)
    else:
        mappings['local-hab'][site.platform] = PurePosixPath(cfg_root)

    # Ensure consistent testing across platforms. cfg has the current os's
    # file paths instead of what is stored in frozen.json
    cfg.frozen_data["aliases"]["linux"]["dcc"] = "TEST_DIR_NAME//the_dcc"
    cfg.frozen_data["aliases"]["windows"]["dcc"] = "TEST_DIR_NAME\\the_dcc.exe"

    ret = cfg.freeze()
    check_file = config_root / "frozen.json"
    check = utils.json.load(check_file.open())
    # Apply template values so we can easily check against frozen.
    update_config(check, cfg_root, site.platform)

    assert ret == check


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
    assert cfg.frozen_data["environment"] == frozen_config["environment"]

    # Check various class overrides
    assert cfg._dump_versions(cfg.versions) == sorted(frozen_config["versions"])
    assert cfg.aliases == frozen_config["aliases"][cfg._platform]
    assert "dcc" in cfg.aliases
    assert cfg.fullpath == "not_set/distros"


def test_decode_freeze(config_root, resolver):
    check_file = config_root / "frozen_no_distros.json"
    checks = utils.json.load(check_file.open())
    v1 = checks["version1"]
    raw = checks["raw"]

    # Check that a v1 freeze is decoded correctly
    assert utils.decode_freeze(v1) == raw
    # Check that padded versions are also supported
    assert utils.decode_freeze(f'v01:{v1[3:]}') == raw

    # Check that non-versioned freeze strings raise an helpful exception
    for check in (
        # Missing `v1:`
        v1[3:],
        # Missing `v'
        f'1:{v1[3:]}',
    ):
        with pytest.raises(ValueError) as excinfo:
            utils.decode_freeze(check)
        assert (
            str(excinfo.value)
            == "Missing freeze version information in format `v0:...`"
        )

    # Check that versions other than numbers raise a helpful exception
    with pytest.raises(ValueError) as excinfo:
        utils.decode_freeze(f'vINVALID:{v1[3:]}')
    assert str(excinfo.value) == 'Version INVALID is not valid.'

    # check that other version encodings return nothing
    assert utils.decode_freeze(f'v2:{v1[3:]}') is None
    assert utils.decode_freeze(f'v0:{v1[3:]}') is None


def test_encode_freeze(config_root, resolver):
    cfg = resolver.resolve('not_set/no_distros')
    check_file = config_root / "frozen_no_distros.json"
    checks = utils.json.load(check_file.open())

    # Check that the dict contains the expected contents
    freeze = cfg.freeze()
    assert freeze == checks["raw"]

    # Check that version 1 encoding is correct
    version1 = utils.encode_freeze(freeze, version=1)
    assert version1 == checks["version1"]

    # Check that other version encodings return nothing
    assert utils.encode_freeze(freeze, version=0) is None
    assert utils.encode_freeze(freeze, version=2) is None
