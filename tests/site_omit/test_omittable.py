import pytest

from hab import Resolver, Site, errors


@pytest.fixture
def omit_resolver(config_root):
    """Return a testing resolver with omittable_distros defined in default.
    Does not use habcache files."""
    site = Site([config_root / "site_omit" / "site_omit.json"])
    return Resolver(site=site)


def test_defined(omit_resolver, helpers):
    """The `omittable/defined` config defines both distros and omittable_distros.
    Ensure the versions are resolved correctly and doesn't raise a
    `InvalidRequirementError` exception.
    """
    cfg = omit_resolver.resolve("omittable/defined")
    assert cfg.omittable_distros == [
        "houdini19.5",
        "missing_dcc",
        "non-existent-distro",
    ]

    # An omitted distro still shows up in the distros list
    assert "missing_dcc" in cfg.distros
    assert "non-existent-distro" in cfg.distros

    # Omitted distros that were found show up in versions
    version_names = helpers.distro_names(cfg.versions, True)
    assert set(version_names) == set(
        [
            "houdini19.5",
            "maya2020",
            "the_dcc_plugin_a",
            "the_dcc_plugin_b",
            "the_dcc_plugin_c",
            "the_dcc_plugin_d",
            "the_dcc_plugin_e",
        ]
    )

    # If a distro is not found it won't be in versions and no errors are raised.
    assert "missing_dcc" not in version_names
    assert "non-existent-distro" not in version_names


def test_inherited(omit_resolver, helpers):
    """The `omittable/inherited` config only defines distros but not
    omittable_distros which are inherited from `default`. Ensure the versions
    are resolved correctly and doesn't raise a `InvalidRequirementError` exception.
    """
    # This config defines both distros and omittable_distros inside the file
    cfg = omit_resolver.resolve("omittable/inherited")
    assert cfg.omittable_distros == [
        "missing_dcc",
        "non-existent-distro",
        "the_dcc_plugin_b",
    ]

    # An omitted distro still shows up in the distros list
    assert "missing_dcc" in cfg.distros
    assert "non-existent-distro" in cfg.distros

    # Omitted distros that were found show up in versions
    version_names = helpers.distro_names(cfg.versions, True)
    assert set(version_names) == set(
        [
            "maya2020",
            "the_dcc_plugin_a",
            "the_dcc_plugin_b",
            "the_dcc_plugin_d",
            "the_dcc_plugin_e",
        ]
    )

    # If a distro is not found it won't be in versions and no errors are raised.
    assert "missing_dcc" not in version_names
    assert "non-existent-distro" not in version_names


def test_forced(omit_resolver, helpers):
    """Checks how omittable_distros handle forced_requirements."""

    # Passing a missing non-omittable_distro as a forced_requirement should
    # still raise an error
    with pytest.raises(
        errors.InvalidRequirementError,
        match=r"Unable to find a distro for requirement: missing_dcc",
    ):
        omit_resolver.resolve("omittable/invalid", forced_requirements=["missing_dcc"])

    # Valid forced_requirements are respected normally
    cfg = omit_resolver.resolve(
        "omittable/inherited", forced_requirements=["houdini19.5", "missing_dcc"]
    )

    # An omitted distro still shows up in the distros list
    assert "missing_dcc" in cfg.distros
    assert "non-existent-distro" in cfg.distros

    # But one added by forced_requiremnts don't show up there
    assert "houdini19.5" not in cfg.distros

    # Forced and omitted distros that were found show up in versions
    version_names = helpers.distro_names(cfg.versions, True)
    assert set(version_names) == set(
        [
            "houdini19.5",
            "maya2020",
            "the_dcc_plugin_a",
            "the_dcc_plugin_b",
            "the_dcc_plugin_d",
            "the_dcc_plugin_e",
        ]
    )

    # If a distro is not found it won't be in versions and no errors are raised.
    assert "missing_dcc" not in version_names
    assert "non-existent-distro" not in version_names


def test_pure_default(omit_resolver, helpers):
    """The `omittable/undefined` config is not explicitly defined so all values
    are inherited from `default`. Ensure the versions are resolved correctly
    and doesn't raise a `InvalidRequirementError` exception.
    """
    # This config and its parent are not defined, both distros and omittable_distros
    # are only defined in the default configuration.
    cfg = omit_resolver.resolve("omittable/undefined")
    assert cfg.omittable_distros == [
        "missing_dcc",
        "non-existent-distro",
        "the_dcc_plugin_b",
    ]

    # An omitted distro still shows up in the distros list
    assert "missing_dcc" not in cfg.distros
    assert "non-existent-distro" not in cfg.distros

    # Omitted distros that were found show up in versions
    version_names = helpers.distro_names(cfg.versions, True)
    assert set(version_names) == set(
        [
            "houdini19.5",
            "maya2020",
            "the_dcc_plugin_a",
            "the_dcc_plugin_b",
            "the_dcc_plugin_c",
            "the_dcc_plugin_d",
            "the_dcc_plugin_e",
        ]
    )

    # If a distro is not found it won't be in versions and no errors are raised.
    assert "missing_dcc" not in version_names
    assert "non-existent-distro" not in version_names


def test_missing_required(omit_resolver):
    """The `omittable/invalid` config requires the `missing_dcc` distro but does
    not add it to `omittable_distros`, and will raise `InvalidRequirementError`.
    """
    with pytest.raises(
        errors.InvalidRequirementError,
        match=r"Unable to find a distro for requirement: missing_dcc",
    ):
        omit_resolver.resolve("omittable/invalid")
