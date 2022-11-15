import pytest

from hab import NotSet, utils
from hab.parsers import UnfrozenConfig
from hab.utils import dumps_json, json


def test_json_dumps():
    """Check that dumps_json returns the expected results for non-standard
    objects."""
    data = {"NotSet": NotSet}
    assert dumps_json(data) == '{"NotSet": null}'
    assert dumps_json(data, indent=2) == '\n'.join(
        [
            '{',
            '  "NotSet": null',
            '}',
        ]
    )


def test_freeze(config_root, resolver):
    cfg = resolver.resolve("not_set/distros")
    # Ensure consistent testing across platforms. cfg has the current os's
    # file paths instead of what is stored in frozen.json
    cfg.frozen_data["aliases"]["linux"]["dcc"] = "TEST_DIR_NAME//the_dcc"
    cfg.frozen_data["aliases"]["windows"]["dcc"] = "TEST_DIR_NAME\\the_dcc.exe"

    ret = cfg.freeze()
    check_file = config_root / "frozen.json"
    check = json.load(check_file.open())
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
