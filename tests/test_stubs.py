import sys

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

from hab import NotSet, Resolver, Site
from hab.errors import InvalidRequirementError
from hab.parsers import DistroVersion, StubDistroVersion

dep_logic_supported = sys.version_info >= (3, 8)
dep_reason = "Library does not support python version"


@pytest.fixture
def site_stub(config_root):
    return Site([config_root / "site" / "site_stub.json"])


@pytest.fixture
def site_stub_a(config_root):
    return Site(
        [
            config_root / "site" / "site_stub_a.json",
            config_root / "site" / "site_stub.json",
        ]
    )


class TestSite:
    site_stub_check = {
        "distro1.0": {},
        "invalid": {},
        "maya2024": {},
        "the_dcc_plugin_a": {"limit": ">=1.0,!=2.*,<4.0"},
        "unset-by-config": {},
        "unset-by-null": {},
        "unset-by-site": {},
    }

    def test_default(self, uncached_resolver):
        assert uncached_resolver.site["stub_distros"] == {}

    def test_site_stub(self, site_stub):
        """Test parsing site_stub.json file, it does not inherit any settings."""
        assert site_stub["stub_distros"] == self.site_stub_check

    def test_site_stub_a(self, site_stub_a):
        """Test parsing site_stub_a.json file that inherits from site_stub.json."""
        assert site_stub_a["stub_distros"] == {
            "distro*": {},
            "distro1.0": {},
            "invalid": {},
            "maya2024": {},
            "the_dcc_plugin_a": {"limit": ">=1.0,!=2.*,<4.0"},
            "unset-by-config": {},
            "unset-by-null": {},
            # site_stub_a, unsets this stub, making it required again.
            "unset-by-site": None,
        }

    def test_stub_distros_override(self, site_stub):
        """Test using `Site.stub_distros_override` to modify the site"""
        overrides = {
            "set": {
                "added-by-override": {},
                "maya2024": {"limit": "==2025.*"},
                "unset-by-null": None,
            },
            "unset": ["unset-by-null"],
        }
        # Verify that our check dict matches the stub_site.json definition
        assert site_stub["stub_distros"] == self.site_stub_check
        # Get the instance of an value stored inside the site for deepcopy checks
        check_object = site_stub["stub_distros"]["invalid"]
        assert site_stub["stub_distros"]["invalid"] is check_object

        with site_stub.stub_distros_override(overrides):
            # Verify that the overrides were applied correctly
            assert site_stub["stub_distros"] == {
                "added-by-override": {},
                "distro1.0": {},
                "invalid": {},
                "maya2024": {"limit": "==2025.*"},
                "the_dcc_plugin_a": {"limit": ">=1.0,!=2.*,<4.0"},
                "unset-by-config": {},
                "unset-by-null": None,
                "unset-by-site": {},
            }
            # Verify that the dictionary was created using deepcopy. This ensures
            # that this context doesn't change the original definition
            assert site_stub["stub_distros"]["invalid"] is not check_object

        # The original stub_distros is restored after exit including same instance
        assert site_stub["stub_distros"] == self.site_stub_check
        assert site_stub["stub_distros"]["invalid"] is check_object


class TestDistro:
    def test_stub_cache(self, site_stub_a):
        """Verify that removing the stub cache cleans up the distros forest."""
        resolver = Resolver(site_stub_a)

        # The stub is not created by default
        distro = resolver.distros["maya2024"]
        assert distro.stub is None

        # Create the stub by requesting a invalid distro version
        maya_stub = distro.latest_version(Requirement("maya2024==1.0"))
        assert distro.stub is maya_stub
        assert isinstance(maya_stub, StubDistroVersion)
        # The stub's parent node is the distro in the forest
        assert maya_stub.parent is distro

        # Remove the stub
        distro.stub = None
        # This un-parents maya_stub from its parent removing it from the forest
        assert maya_stub.parent is None
        assert distro.stub is None

        # Re-create the distro as a new instance
        new_stub = distro.latest_version(Requirement("maya2024==1.0"))
        assert isinstance(new_stub, StubDistroVersion)
        assert distro.stub is new_stub
        # A new instance was created separate from the original stub
        assert new_stub is not maya_stub

        # The new stub was added to the forest
        assert new_stub.parent == distro
        assert maya_stub.parent is None
        assert new_stub.name == "maya2024==STUB"
        assert maya_stub.name == "maya2024==STUB"

    @pytest.mark.parametrize(
        "site,requirement,check",
        (
            ("site_stub", "distro1.0", "distro1.0==STUB"),
            ("site_stub_a", "distro1.0", "distro1.0==STUB"),
            # Not a stub for site_stub, but site_stub_a ignores it via wildcard
            pytest.param(
                "site_stub",
                "distro2.0",
                InvalidRequirementError,
                marks=pytest.mark.skipif(not dep_logic_supported, reason=dep_reason),
            ),
            ("site_stub_a", "distro2.0", "distro2.0==STUB"),
            ("site_stub", "invalid", "invalid==STUB"),
            # No stub needed, there is a valid distro installed
            ("site_stub", "maya2024", "maya2024==2024.0"),
            # But this version is not installed
            ("site_stub", "maya2024==2024.2", "maya2024==STUB"),
            # Test the limit argument is correctly applied
            ("site_stub", "the_dcc_plugin_a", "the_dcc_plugin_a==1.1"),
            ("site_stub", "the_dcc_plugin_a==1.0", "the_dcc_plugin_a==1.0"),
            ("site_stub", "the_dcc_plugin_a==1.5", "the_dcc_plugin_a==STUB"),
            pytest.param(
                "site_stub",
                "the_dcc_plugin_a==2.1",
                InvalidRequirementError,
                marks=pytest.mark.skipif(not dep_logic_supported, reason=dep_reason),
            ),
            ("site_stub", "the_dcc_plugin_a==3.0", "the_dcc_plugin_a==STUB"),
            # For a site, the stub is allowed by the parent but removed by the child
            ("site_stub", "unset-by-site", "unset-by-site==STUB"),
            pytest.param(
                "site_stub_a",
                "unset-by-site",
                InvalidRequirementError,
                marks=pytest.mark.skipif(not dep_logic_supported, reason=dep_reason),
            ),
        ),
    )
    def test_latest_version(self, request, site, requirement, check):
        """Test how a specific stub distro requirement is resolved.

        Pass `InvalidRequirementError` for check if this requirement can not be
        made a stub distro.
        """
        site = request.getfixturevalue(site)
        requirement = Requirement(requirement)
        resolver = Resolver(site)

        if check == InvalidRequirementError:
            match = (
                r"Unable to find a distro for requirement:|"
                r"Unable to find a valid version for"
            )
            with pytest.raises(check, match=match):
                resolver.find_distro(requirement)
        else:
            # Verify that the distro.version is set correctly for STUB's
            distro = resolver.find_distro(requirement)
            assert distro.name == check
            if check.endswith("==STUB"):
                check_version = "0+stub"
            else:
                check_version = str(check).split("==")[1]
            assert distro.version == Version(check_version)


class TestConfig:
    def test_updating(self, site_stub):
        """Verifies that we can replace the stub_distros setting on a config."""
        resolver = Resolver(site_stub)

        # Verify this config doesn't have stub_distros defined
        cfg = resolver.resolve("app/aliased")
        assert cfg.stub_distros is NotSet

        # Verify that we can set it to a new value
        cfg.stub_distros = {"test": None}
        assert cfg.stub_distros == {"test": None}

    def test_exceptions(self, site_stub, site_stub_a, helpers):
        """Test that the expected exceptions are raised when resolving a config."""
        resolver = Resolver(site_stub)

        # This config and site combination requires one or more missing distros
        with pytest.raises(
            InvalidRequirementError,
            match="Unable to find a distro for requirement: distro2.0",
        ):
            resolver.resolve("stub")

        # This config and site combination addresses the previously missing distro
        # but still is missing another.
        resolver = Resolver(site_stub_a)
        with pytest.raises(
            InvalidRequirementError,
            match="Unable to find a distro for requirement: another",
        ):
            resolver.resolve("stub")

        # The override URI config updates stub_distros to enable stub for another
        cfg = resolver.resolve("stub/override")
        assert "another==STUB" in helpers.distro_names(cfg.versions)

    def test_config_resolve(self, site_stub_a, helpers):
        resolver = Resolver(site_stub_a)

        # Verify that the expected versions were found including stubs.
        cfg = resolver.resolve("stub/override")
        assert helpers.distro_names(cfg.versions) == [
            "the_dcc_plugin_a==1.1",
            "the_dcc_plugin_e==1.1",
            "the_dcc_plugin_d==1.1",
            "the_dcc_plugin_b==1.1",
            "the_dcc_plugin_c==1.1",
            "the_dcc==1.2",
            "houdini19.5==19.5.493",
            "maya2020==2020.1",
            "invalid==STUB",
            "maya2024==STUB",
            "distro1.0==STUB",
            "distro2.0==STUB",
            "another==STUB",
        ]

        # Verify the correct StubDistroVersion and DistroVersion classes are used
        found_maya = False
        found_the_dcc_plugin_a = False
        for distro in cfg.versions:
            if distro.distro_name == "maya2024":
                assert isinstance(distro, StubDistroVersion)
                found_maya = True
                # Verify that the Distro.stub was cached on this object
                assert resolver.distros["maya2024"].stub == distro
            if distro.distro_name == "the_dcc_plugin_a":
                assert isinstance(distro, DistroVersion)
                found_the_dcc_plugin_a = True
                # The Distro.stub cache is only created if actually required
                assert resolver.distros["the_dcc_plugin_a"].stub is None

        assert found_maya is True
        assert found_the_dcc_plugin_a is True
