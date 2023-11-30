import datetime
import json
import logging
from pathlib import Path

from . import utils

logger = logging.getLogger(__name__)


class UriObj:
    def __init__(self, uri=None, timedout=False):
        self._uri = uri
        self._timedout = timedout

    def __str__(self):
        if self.uri is None:
            return ""
        else:
            return self.uri

    @property
    def timedout(self):
        return self._timedout

    @property
    def uri(self):
        return self._uri


class UserPrefs(dict):
    """Stores/restores hab user preferences in a json file."""

    def __init__(self, resolver):
        self.resolver = resolver
        self._is_loaded = False

    @property
    def enabled(self):
        """Returns if user preferences are enabled.

        The resolver's site config value "prefs_default" controls if preferences
        can be enabled and the default value(uses index 0). If set to "disabled"
        this will always return False. The cli enable/disable flags are used to
        enable or disable the default value(--prefs/--no-prefs). Defaults to
        "disabled".
        """
        try:
            return self._enabled
        except AttributeError:
            # This is the first call, return the default value
            self.enabled = None
            return self._enabled

    @enabled.setter
    def enabled(self, prefs):
        # Site resolves "prefs_default" into a list of options, the first item
        # in the list is respected
        default = self.resolver.site.get("prefs_default", [])
        if default:
            default = default[0]
            # Convert command flag strings to bolean values
            default = True if default == "--prefs" else default
            default = False if default == "--no-prefs" else default
        else:
            default = "disabled"

        if default == "disabled":
            # If the site disables preferences always use False
            logger.debug("Pref loading disabled by site")
            self._enabled = False
        elif prefs is None:
            logger.debug(f"Pref loading defaulting to {default} by site")
            self._enabled = default
        else:
            logger.debug(f"Pref loading set to {prefs}")
            self._enabled = prefs

    @property
    def filename(self):
        """The file path to load/save prefs from using json. Defaults to
        `Platform.user_prefs_filename()`.
        """
        try:
            return self._filename
        except AttributeError:
            self._filename = utils.Platform.user_prefs_filename()
            return self._filename

    @filename.setter
    def filename(self, value):
        self._filename = Path(value)

    def load(self, force=False):
        """Load user preferences from self.filename if they haven't already
        been loaded. Does not use pyjson5 as this file is entirely managed by hab.

        Args:
            force (bool, optional): Force re-loading of preferences.

        Returns:
            bool: If self.filename exists.
        """
        if not self.filename.exists():
            return False

        if self._is_loaded and not force:
            return True

        with self.filename.open() as fle:
            try:
                # NOTE: This file is always saved using the native json library
                # there is no reason to support json5 encoded files here.
                data = json.load(fle)
            except ValueError as error:
                # When encountering corrupt saved user pref data, clear and
                # reset the user prefs. Warn about it this isn't entirely hidden
                logger.warning("User pref file corrupt, resetting.")
                logger.info("User pref exception suppressed:", exc_info=error)
                data = {}
            self.update(data)
            self._is_loaded = True
        return True

    def save(self):
        """Save user preferences to self.filename. Does not use pyjson5 as this
        file is entirely managed by hab.
        """
        with self.filename.open("w") as fle:
            return json.dump(self, fle, indent=4, cls=utils.HabJsonEncoder)

    @classmethod
    def _fromisoformat(cls, value):
        """Calls `datetime.fromisoforamt` if possible otherwise replicates
        its basic requirements (for python 3.6 support).
        """
        if isinstance(value, datetime.datetime):
            return value
        try:
            return datetime.datetime.fromisoformat(value)
        except AttributeError:
            iso_format = r"%Y-%m-%dT%H:%M:%S.%f"
            return datetime.datetime.strptime(value, iso_format)

    def uri_check(self):
        """Returns the uri saved in preferences. It will only do that if enabled
        and uri_is_timedout allow it. Returns None otherwise. This will call load
        to ensure the preference file has been loaded.
        """
        if self.enabled:
            # Ensure the preferences are loaded.
            self.load()
            uri = self.get("uri")
            if uri:
                return UriObj(uri, self.uri_is_timedout)
        return UriObj()

    @property
    def uri(self):
        return self.uri_check().uri

    @uri.setter
    def uri(self, uri):
        if self.enabled:
            # Ensure the preferences are loaded.
            self.load()
            self["uri"] = uri
            self["uri_last_changed"] = datetime.datetime.today()
            self.save()
            logger.debug(f"User prefs saved to {self.filename}")

    @property
    def uri_last_changed(self):
        value = self.get("uri_last_changed")
        if value is None:
            return value
        return self._fromisoformat(value)

    @property
    def uri_is_timedout(self):
        """Returns True if "uri_last_changed" is stored on prefs and that time is
        longer than uri_timeout."""

        uri_last_changed = self.uri_last_changed

        if uri_last_changed:
            current = datetime.datetime.today()
            timeout = self.uri_timeout
            if timeout and current - uri_last_changed > timeout:
                logger.debug(f"Saved URI exceeded timeout of {timeout}")
                return True

        return False

    @property
    def uri_timeout(self):
        """Returns a datetime.timedelta object if the site configuration defines
        the "prefs_uri_timeout" setting. If set, this should be a dictionary of
        kwargs to construct the timedelta. Otherwise returns None.
        """
        timeout = self.resolver.site.get("prefs_uri_timeout")
        if timeout:
            return datetime.timedelta(**timeout)
        return None
