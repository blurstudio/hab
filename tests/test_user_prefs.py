import datetime
import json
import logging

import pytest

from hab import user_prefs, utils


def test_user_prefs_filename():
    """Check that user_prefs_filename generates the expected file paths."""
    # Check the default for filename
    path = utils.Platform.user_prefs_filename()
    assert path.name == ".hab_user_prefs.json"

    # Check overriding filename
    new = utils.Platform.user_prefs_filename(filename="test.json")
    assert new == path.parent / "test.json"


def test_configure_logging(monkeypatch, tmpdir):
    # Ensure we can read/write logging prefs, but using the test dir.
    monkeypatch.setenv("HOME", str(tmpdir))
    monkeypatch.setenv("LOCALAPPDATA", str(tmpdir))

    logger = logging.getLogger("hab.test")
    default = utils.Platform.user_prefs_filename(".hab_logging_prefs.json")
    custom = tmpdir / "test.json"

    logging_cfg = {
        "version": 1,
        "incremental": True,
        "loggers": {"hab.test": {"level": 10}},
    }

    # The default file doesn't exist yet, no configuration is loaded
    assert not utils.Platform.configure_logging()
    # The logger's level is not configured yet
    assert logger.level == 0

    # Create the configuration and ensure it gets loaded
    with default.open("w") as fle:
        json.dump(logging_cfg, fle)
    assert utils.Platform.configure_logging()
    # The logger had its level set to 10 by the config
    assert logger.level == 10

    # Check that passing a filename is respected
    logging_cfg["loggers"]["hab.test"]["level"] = 30
    with custom.open("w") as fle:
        json.dump(logging_cfg, fle)
    assert utils.Platform.configure_logging(filename=custom)
    # The logger had its level set to 10 by the config
    assert logger.level == 30


def test_filename(uncached_resolver, tmpdir):
    prefs = uncached_resolver.user_prefs(load=True)
    # Defaults to Platform path
    assert prefs.filename == utils.Platform.user_prefs_filename()

    filename = tmpdir / ".hab_user_prefs.json"
    prefs.filename = filename
    assert prefs.filename == filename

    # If the file doesn't exist on disk, load returns False
    assert prefs.load() is False


def test_enabled_no_default(uncached_resolver):
    """If prefs_default is not specified default to disabled."""
    uncached_resolver.site.pop("prefs_default", None)
    prefs = user_prefs.UserPrefs(uncached_resolver)
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
def test_enabled(uncached_resolver, setting, default, value, check):
    uncached_resolver.site["prefs_default"] = setting
    prefs = user_prefs.UserPrefs(uncached_resolver)

    assert prefs.enabled == default
    prefs.enabled = value
    assert prefs.enabled == check


def test_timeout(uncached_resolver):
    uncached_resolver.site.pop("prefs_uri_timeout", None)
    prefs = user_prefs.UserPrefs(uncached_resolver)

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
    uncached_resolver.site["prefs_uri_timeout"] = dict(minutes=5)
    assert prefs.uri_timeout == datetime.timedelta(minutes=5)
    assert prefs.uri_is_timedout is False
    set_uri_last_changed(minutes=6)
    assert prefs.uri_is_timedout is True

    uncached_resolver.site["prefs_uri_timeout"] = dict(days=30)
    assert prefs.uri_timeout == datetime.timedelta(days=30)
    assert prefs.uri_is_timedout is False
    set_uri_last_changed(days=40)
    assert prefs.uri_is_timedout is True


def test_uri(uncached_resolver, tmpdir, monkeypatch):
    uncached_resolver.site.pop("prefs_uri_timeout", None)

    # Force the prefs to be saved into the test directory.
    if utils.Platform.name() == "windows":
        monkeypatch.setenv("LOCALAPPDATA", str(tmpdir))
    else:
        monkeypatch.setenv("HOME", str(tmpdir))
    # Ensure we are using the modified filepath
    prefs_a = user_prefs.UserPrefs(uncached_resolver)
    assert prefs_a.filename.parent == tmpdir

    # No preferences are saved
    prefs_b = user_prefs.UserPrefs(uncached_resolver)
    prefs_b._enabled = False
    assert prefs_b.uri is None

    # Preferences store an uri
    prefs_b["uri"] = "app/aliased"
    prefs_b.save()
    prefs_c = user_prefs.UserPrefs(uncached_resolver)
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

    prefs_d = user_prefs.UserPrefs(uncached_resolver)
    prefs_d._enabled = True
    # Timeout has not expired
    uncached_resolver.site["prefs_uri_timeout"] = dict(hours=2)
    assert prefs_d.uri_check().timedout is False
    # Timeout has expired
    uncached_resolver.site["prefs_uri_timeout"] = dict(minutes=5)
    assert prefs_d.uri_check().timedout is True

    # Check that uri.setter is processed correctly
    prefs_e = user_prefs.UserPrefs(uncached_resolver)

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


@pytest.mark.parametrize(
    "test_text",
    (
        # File was opened in write mode but no contents written
        None,
        # Process was killed half way through writing json output.
        '{\n    "uri": "app',
    ),
)
def test_corruption(uncached_resolver, tmpdir, monkeypatch, caplog, test_text):
    """Check how UserPrefs handles trying to load an incomplete or empty existing
    json document.
    """
    caplog.set_level(logging.INFO)

    def assert_log_exists(level, msg):
        for record in caplog.records:
            if record.levelname != level:
                continue
            if msg in record.message:
                print(record)
                break
        else:
            raise AssertionError(
                f"No logging message was made matching: {level} and {msg}"
            )

    # TODO: This duplicated code should probably be moved into a fixture
    # Force the prefs to be saved into the test directory.
    if utils.Platform.name() == "windows":
        monkeypatch.setenv("LOCALAPPDATA", str(tmpdir))
    else:
        monkeypatch.setenv("HOME", str(tmpdir))
    # Ensure we are using the modified filepath
    prefs = user_prefs.UserPrefs(uncached_resolver)
    assert prefs.filename.parent == tmpdir

    prefs_file = tmpdir / ".hab_user_prefs.json"

    # Create a empty file that won't resolve properly for json.
    with prefs_file.open("w") as fle:
        if test_text:
            fle.write(test_text)

    # Check that the expected log messages are emitted when invalid
    # json file contents are encountered
    caplog.clear()
    prefs = user_prefs.UserPrefs(uncached_resolver)
    # Even with invalid contents True will be returned
    assert prefs.load()
    # When corrupt prefs are encountered, default empty dict results
    assert prefs == {}

    assert_log_exists("WARNING", "User pref file corrupt, resetting.")
    assert_log_exists("INFO", "User pref exception suppressed:")
