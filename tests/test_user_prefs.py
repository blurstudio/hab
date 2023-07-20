import datetime

import pytest

from hab import user_prefs, utils


def test_filename(resolver, tmpdir):
    prefs = resolver.user_prefs(load=True)
    # Defaults to Platform path
    assert prefs.filename == utils.Platform.user_prefs_filename()

    filename = tmpdir / ".hab_user_prefs.json"
    prefs.filename = filename
    assert prefs.filename == filename

    # If the file doesn't exist on disk, load returns False
    assert prefs.load() is False


def test_enabled_no_default(resolver):
    """If prefs_default is not specified default to disabled."""
    resolver.site.pop("prefs_default", None)
    prefs = user_prefs.UserPrefs(resolver)
    assert prefs.enabled is False


@pytest.mark.parametrize(
    "setting,default,value,check",
    (
        # If prefs_default is disabled, the result is False for all values
        (["disabled"], False, None, False),
        (["disabled"], False, True, False),
        (["disabled"], False, False, False),
        # Enabling prefs by default
        (["--prefs"], True, None, True),
        (["--prefs"], True, True, True),
        (["--prefs"], True, False, False),
        ([True], True, True, True),
        # Disabling prefs by default
        (["--no-prefs"], False, None, False),
        (["--no-prefs"], False, True, True),
        (["--no-prefs"], False, False, False),
        ([False], False, False, False),
    ),
)
def test_enabled(resolver, setting, default, value, check):
    resolver.site["prefs_default"] = setting
    prefs = user_prefs.UserPrefs(resolver)

    assert prefs.enabled == default
    prefs.enabled = value
    assert prefs.enabled == check


def test_timeout(resolver):
    resolver.site.pop("prefs_uri_timeout", None)
    prefs = user_prefs.UserPrefs(resolver)

    def set_uri_last_changed(**kwargs):
        d = datetime.datetime.today()
        d = d - datetime.timedelta(**kwargs)
        prefs["uri_last_changed"] = d.isoformat()

    # uri_is_timedout works if last_chanded is not set
    prefs.pop("uri_last_changed", None)
    assert prefs.uri_is_timedout is False

    # prefs_uri_timeout is not set
    set_uri_last_changed(minutes=3)
    assert prefs.uri_timeout is None

    # prefs_uri_timeout enables uri timeout
    resolver.site["prefs_uri_timeout"] = dict(minutes=5)
    assert prefs.uri_timeout == datetime.timedelta(minutes=5)
    assert prefs.uri_is_timedout is False
    set_uri_last_changed(minutes=6)
    assert prefs.uri_is_timedout is True

    resolver.site["prefs_uri_timeout"] = dict(days=30)
    assert prefs.uri_timeout == datetime.timedelta(days=30)
    assert prefs.uri_is_timedout is False
    set_uri_last_changed(days=40)
    assert prefs.uri_is_timedout is True


def test_uri(resolver, tmpdir, monkeypatch):
    resolver.site.pop("prefs_uri_timeout", None)

    # Force the prefs to be saved into the test directory.
    if utils.Platform.name() == "windows":
        monkeypatch.setenv("LOCALAPPDATA", str(tmpdir))
    else:
        monkeypatch.setenv("HOME", str(tmpdir))
    # Ensure we are using the modified filepath
    prefs_a = user_prefs.UserPrefs(resolver)
    assert prefs_a.filename.parent == tmpdir

    # No preferences are saved
    prefs_b = user_prefs.UserPrefs(resolver)
    prefs_b._enabled = False
    assert prefs_b.uri is None

    # Preferences store an uri
    prefs_b["uri"] = "app/aliased"
    prefs_b.save()
    prefs_c = user_prefs.UserPrefs(resolver)
    # Prefs are disabled
    prefs_c._enabled = False
    assert prefs_c.uri is None
    # Prefs are enabled
    prefs_c._enabled = True
    assert prefs_c.uri == "app/aliased"

    # Preferences store timeout information
    last = datetime.datetime.today()
    last = last - datetime.timedelta(hours=1)
    prefs_c["uri_last_changed"] = last.isoformat()
    prefs_c.save()

    prefs_d = user_prefs.UserPrefs(resolver)
    prefs_d._enabled = True
    # Timeout has not expired
    resolver.site["prefs_uri_timeout"] = dict(hours=2)
    assert prefs_d.uri_check().timedout is False
    # Timeout has expired
    resolver.site["prefs_uri_timeout"] = dict(minutes=5)
    assert prefs_d.uri_check().timedout is True

    # Check that uri.setter is processed correctly
    prefs_e = user_prefs.UserPrefs(resolver)

    # uri.setter is ignored if prefs are disabled
    prefs_e._enabled = False
    prefs_e.uri = "app/aliased/mod"
    assert "uri" not in prefs_e
    assert prefs_e.uri is None

    # uri.setter updates the uri and sets the timestamp
    assert "uri_last_changed" not in prefs_e
    prefs_e._enabled = True
    assert "uri" not in prefs_e
    prefs_e.uri = "app/aliased/mod"
    assert prefs_e["uri"] == "app/aliased/mod"
    assert prefs_e.uri == "app/aliased/mod"
    # The timeout was properly stored
    assert prefs_e["uri_last_changed"].date() == datetime.date.today()

    # Check that the file was actually written
    assert prefs_e.filename.exists()
    assert prefs_e.filename == utils.Platform.user_prefs_filename()

    # Check if UriObj.__str__() is passing the uri contents
    prefs_g = user_prefs.UriObj("test/uri")
    assert prefs_g.__str__() == "test/uri"

    # Check UriObj.__str__ returns a string even if uri is None
    prefs_g = user_prefs.UriObj()
    assert isinstance(prefs_g.__str__(), str)
