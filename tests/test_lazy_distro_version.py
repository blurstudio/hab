import pytest
from packaging.requirements import Requirement
from packaging.version import Version

from hab import DistroMode
from hab.errors import InstallDestinationExistsError
from hab.parsers.lazy_distro_version import DistroPath, LazyDistroVersion


def test_distro_path(zip_distro_sidecar, helpers, tmp_path):
    resolver = helpers.render_resolver(
        "site_distro_zip_sidecar.json",
        tmp_path,
        zip_root=zip_distro_sidecar.root.as_posix(),
    )
    with resolver.distro_mode_override(DistroMode.Downloaded):
        distro = resolver.find_distro("dist_a==0.2")

    # Passing root as a string converts it to a pathlib.Path object.
    dpath = DistroPath(
        distro, str(tmp_path), relative="{distro_name}-v{version}", site=resolver.site
    )
    # Test that the custom relative string, it used to generate root
    assert dpath.root == tmp_path / "dist_a-v0.2"
    assert dpath.hab_filename == tmp_path / "dist_a-v0.2" / ".hab.json"

    # If site and relative are not passed the default is used
    dpath = DistroPath(distro, tmp_path)
    assert dpath.root == tmp_path / "dist_a" / "0.2"
    assert dpath.hab_filename == tmp_path / "dist_a" / "0.2" / ".hab.json"

    # Test that site settings are respected when not passing relative
    resolver.site.downloads["relative_path"] = "parent/{distro_name}/child/{version}"
    dpath = DistroPath(distro, tmp_path, site=resolver.site)
    assert dpath.root == tmp_path / "parent" / "dist_a" / "child" / "0.2"
    assert (
        dpath.hab_filename
        == tmp_path / "parent" / "dist_a" / "child" / "0.2" / ".hab.json"
    )


def test_is_lazy(zip_distro_sidecar, helpers, tmp_path):
    """Check that a LazyDistroVersion doesn't automatically load all data."""
    resolver = helpers.render_resolver(
        "site_distro_zip_sidecar.json",
        tmp_path,
        zip_root=zip_distro_sidecar.root.as_posix(),
    )
    with resolver.distro_mode_override(DistroMode.Downloaded):
        distro = resolver.find_distro("dist_a==0.1")

    frozen_data = dict(
        context=["dist_a"],
        name="dist_a==0.1",
        version=Version("0.1"),
    )
    filename = zip_distro_sidecar.root / "dist_a_v0.1.hab.json"

    # The find_distro call should have called load but does not actually load data
    assert isinstance(distro, LazyDistroVersion)
    assert distro._loaded is False
    assert distro.context == ["dist_a"]
    assert distro.filename == filename
    assert distro.frozen_data == frozen_data
    assert distro.name == "dist_a==0.1"

    # Calling _ensure_loaded actually loads the full distro from the finder's data
    data = distro._ensure_loaded()
    assert distro._loaded is True
    assert isinstance(data, dict)
    assert distro.name == "dist_a==0.1"

    # If called a second time, then nothing extra is done and no data is returned.
    assert distro._ensure_loaded() is None


def test_bad_kwargs():
    """Test that the proper error is raised if you attempt to init with a filename."""
    match = "Passing filename to this class is not supported."
    with pytest.raises(ValueError, match=match):
        LazyDistroVersion(None, None, "filename")

    with pytest.raises(ValueError, match=match):
        LazyDistroVersion(None, None, filename="a/filename")


@pytest.mark.parametrize(
    "prop,check",
    (("distros", {"dist_b": Requirement("dist_b")}),),
)
def test_lazy_hab_property(prop, check, zip_distro_sidecar, helpers, tmp_path):
    """Check that a LazyDistroVersion doesn't automatically load all data."""
    resolver = helpers.render_resolver(
        "site_distro_zip_sidecar.json",
        tmp_path,
        zip_root=zip_distro_sidecar.root.as_posix(),
    )
    with resolver.distro_mode_override(DistroMode.Downloaded):
        distro = resolver.find_distro("dist_a==0.2")

    # Calling a lazy getter ensures the data is loaded
    assert distro._loaded is False
    value = getattr(distro, prop)
    assert distro._loaded is True
    assert value == check

    # You can call the lazy getter repeatedly
    value = getattr(distro, prop)
    assert value == check


def test_install(zip_distro_sidecar, helpers, tmp_path):
    """Check that a LazyDistroVersion doesn't automatically load all data."""
    resolver = helpers.render_resolver(
        "site_distro_zip_sidecar.json",
        tmp_path,
        zip_root=zip_distro_sidecar.root.as_posix(),
    )
    with resolver.distro_mode_override(DistroMode.Downloaded):
        distro = resolver.find_distro("dist_a==0.2")
    dest_root = resolver.site.downloads["install_root"]
    distro_root = dest_root / "dist_a" / "0.2"
    hab_json = distro_root / ".hab.json"

    # The distro is not currently installed. This also tests that it can
    # auto-cast to DistroPath
    assert not distro.installed(dest_root)

    # Install will clear the cache, ensure its populated
    assert resolver._downloadable_distros is not None
    # Install the distro using LazyDistroVersion
    distro.install(dest_root)
    assert distro.installed(dest_root)
    assert hab_json.exists()
    # Check that the cache was cleared by the install function
    assert resolver._downloadable_distros is None

    # Test that if the distro is already installed, an error is raised
    with pytest.raises(InstallDestinationExistsError) as excinfo:
        distro.install(dest_root)
    assert excinfo.value.filename == distro_root

    # Test forced replacement of an existing distro by creating an extra file
    extra_file = distro_root / "extra_file.txt"
    extra_file.touch()
    # This won't raise the exception, but will remove the old distro
    distro.install(dest_root, replace=True)
    assert hab_json.exists()
    assert distro.installed(dest_root)

    assert not extra_file.exists()
