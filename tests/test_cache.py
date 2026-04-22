import json
from pathlib import Path

from hab import Resolver, Site
from hab.cache import Cache
from hab.parsers import Config, DistroVersion, HabBase


def test_cached_keys(uncached_resolver):
    check = {
        "config_paths": ("*.json", Config),
        "distro_paths": ("*/.hab.json", DistroVersion),
    }

    cache = uncached_resolver.site.cache
    # Container variable is not set by default
    assert not hasattr(cache, "_cached_keys")
    # On first call generates the correct return value
    assert cache.cached_keys == check
    # And stored the value in the container variable
    assert hasattr(cache, "_cached_keys")

    # Verify that the cached value is returned once generated
    cache._cached_keys = "Test value"
    assert cache.cached_keys == "Test value"


def test_site_cache_path(config_root, uncached_resolver, tmpdir):
    cache = uncached_resolver.site.cache

    # Test default
    site_file = Path(tmpdir) / "test.json"
    assert cache.cache_template == "{stem}.habcache"
    assert cache.site_cache_path(site_file) == tmpdir / "test.habcache"

    # Test that cache_template is respected
    cache.cache_template = "<{stem}>.ext"
    assert cache.site_cache_path(site_file) == tmpdir / "<test>.ext"

    # Test that `site_cache_file_template` site config setting is respected
    site = Site([config_root / "site" / "site_cache_file.json"])
    assert site.cache.cache_template == ".{stem}.hab_cache"


def test_save_cache(config_root, habcached_resolver, helpers):
    """Check that the habcache file generated the expected output text"""
    # Note: This file will need updated as the test configuration is updated
    check_path = config_root / "site_main_check.habcache"
    cache_file = habcached_resolver._test_cache_file
    helpers.compare_files(cache_file, check_path)


def test_save_cache_dest(config_root, tmp_path, helpers):
    """Test the dest argument for Cache.site_cache_path correctly places the file."""
    # Generate the cache and provide easy access to the habcache file path
    site_file = helpers.generate_habcached_site_file(config_root, tmp_path)
    site = Site([site_file])
    resolver = Resolver(site)
    # The path a proper .habcache file would be created.
    cache_file = site.cache.site_cache_path(site_file)

    check_path = config_root / "site_main_check.habcache"
    # The dest argument moves the output to another folder
    dest = tmp_path / "destination"
    dest.mkdir(parents=True, exist_ok=True)
    dest_file = dest / cache_file.name

    # Verify that the site file only exists and no .habcache files
    assert site_file.exists()
    assert not cache_file.exists()
    assert not dest_file.exists()

    # Generate the .habcache file in the dest location
    resolver.site.cache.save_cache(resolver, site_file, dest=dest)

    # Verify that the .habcache file was created in the requested dest
    helpers.compare_files(dest_file, check_path)
    # not next to the site file
    assert not cache_file.exists()
    # and there isn't a site file in the dest folder
    assert not (dest_file.parent / site_file.name).exists()


def test_load_cache(config_root, uncached_resolver, habcached_site_file):
    """Tests non-cached resolved data matches a reference cached version."""
    cached_site = Site([habcached_site_file])
    cached_resolver = Resolver(cached_site)

    # Load the reference cache. In normal operation _cache is None until the
    # first time `.cache` is called, but for this test we won't be doing that.
    cached_site.cache._cache = {}
    cached_site.cache.load_cache(config_root / "site_main_check.habcache")

    # Check that un-cached resolver settings match the reference cache
    for key in ("config_paths", "distro_paths"):
        assert getattr(uncached_resolver, key) == getattr(cached_resolver, key)


def test_unsupported_version_warning(uncached_resolver, tmpdir, caplog):
    cache_file = Path(tmpdir) / "test.habcache"
    warn_msg = (
        "File is using a unsupported habcache version {}. "
        f"Only versions > {{}} are supported, ignoring {cache_file}"
    )

    def _load_cache_version(version, cls=Cache):
        # Generate a test cache for the given version number
        with cache_file.open("w") as fle:
            json.dump({"version": version}, fle)

        cache = cls(uncached_resolver.site)
        cache._cache = {}
        caplog.clear()
        cache.load_cache(cache_file)
        return [rec.message for rec in caplog.records]

    # No warning if version is supported
    assert _load_cache_version(1) == []
    # Warning logged if cache version is newer than supported_version
    assert _load_cache_version(2) == [warn_msg.format(2, 1)]

    # Warning is logged correctly for higher supported versions
    class CacheV2(Cache):
        supported_version = 2

    assert _load_cache_version(1, cls=CacheV2) == []
    assert _load_cache_version(2, cls=CacheV2) == []
    assert _load_cache_version(3, cls=CacheV2) == [warn_msg.format(3, 2)]


def test_cached_method(config_root, habcached_site_file):
    """Test the Cache.cache method options."""
    cached_site = Site([habcached_site_file])
    cache = cached_site.cache
    assert cache.enabled is True

    # At this point _cache is None
    assert cache._cache is None
    # Simulate the cache already being loaded
    cache._cache = "Test value"
    assert cache.cache() == "Test value"

    # Forcing the cache to reload, re-generates a cache
    result = cache.cache(force=True)
    assert isinstance(result, dict)
    assert len(result)

    # Check that disabling caching causes the cache to not be returned
    cache.enabled = False
    assert cache.enabled is False
    result = cache.cache()
    assert isinstance(result, dict)
    assert not len(result)

    # Check that HabBase._cache returns a empty dict.
    assert HabBase(None, None)._cache() == {}


def test_resolver_cache(request, resolver):
    """Tests that cached and uncached resolvers actually use/don't use the cache.

    `uncached_resolver` should not have a habcache file and shouldn't use a cache.
    `habcached_resolver` should have a habcache and uses it.
    """
    # Figure out if this is the cached or uncached resolver test
    is_cached = "habcached_resolver" in request.fixturenames

    # Get the site file path
    assert len(resolver.site.paths) == 1
    site_file = resolver.site.paths[0]
    cache_file = resolver.site.cache.site_cache_path(site_file)

    # The .habcache file should only exist when testing cached
    if is_cached:
        assert cache_file.exists()
    else:
        assert not cache_file.exists()

    # force the resolver to load config/distro information
    resolver.resolve("not_set")

    cache = resolver.site.cache._cache
    if is_cached:
        # This habcache setup has exactly one cached glob string
        assert len(cache["config_paths"]) == 1
        assert len(cache["distro_paths"]) == 1
        # The flat cache has many configs/distros, the test only needs to ensure
        # that we have gotten some results
        assert len(cache["flat"]["config_paths"]) > 10
        assert len(cache["flat"]["distro_paths"]) > 10
    else:
        # If there aren't any habcache files, a default dict is returned
        assert cache == {"flat": {"config_paths": {}, "distro_paths": {}}}
