from packaging.version import InvalidVersion, Version

from .. import NotSet
from ..errors import InvalidVersionError, _IgnoredVersionError
from .distro import Distro
from .hab_base import HabBase
from .meta import hab_property


class DistroVersion(HabBase):
    """A specific version of the loaded `Distro`'s. Including its requirements,
    aliases and environment variables."""

    _context_method = "name"
    _placeholder = Distro

    def __init__(self, *args, **kwargs):
        self._alias_mods = NotSet
        super().__init__(*args, **kwargs)

    def _cache(self):
        return self.resolver.site.cache.distro_paths(flat=True)

    def _resolve_version(self, data, filename):
        """Sets and returns self.version to the correct value for this distro.

        This resolves the version from the several ways it can be stored to
        simplify deployment and development. See InvalidVersionError for details
        on how distros version can be set.

        Raises:
            _IgnoredVersionError: Internal use, this version should not be processed.
            InvalidVersionError: Raised if the version could not be resolved.
        """
        version_txt = self.dirname / ".hab_version.txt"

        if "version" in data:
            self.version = data["version"]
            return self.version
        elif version_txt.exists():
            self.version = version_txt.open().read().strip()
            return self.version

        # If version is not defined in json data extract it from the parent
        # directory name. This allows for simpler distribution without needing
        # to modify version controlled files.
        try:
            self.version = self.dirname.name
            return self.version
        except InvalidVersion:
            """The parent directory was not a valid version, attempt to get a
            version using setuptools_scm.
            """
            try:
                from setuptools_scm import get_version
            except ImportError as error:
                raise InvalidVersionError(filename, error=error) from None

            def check_ignored_version():
                if self.dirname.name in self.resolver.ignored:
                    # This object is not added to the forest until super is called
                    raise _IgnoredVersionError(
                        'Skipping "{}" its dirname is in the ignored list.'.format(
                            filename
                        )
                    ) from None

            try:
                self.version = get_version(
                    root=self.dirname, version_scheme="release-branch-semver"
                )
                return self.version
            except LookupError:
                check_ignored_version()
                raise InvalidVersionError(filename) from None
            except Exception as error:
                check_ignored_version()
                # To make debugging easier include the original exception
                raise InvalidVersionError(filename, error=error) from None

    @hab_property()
    def aliases(self):
        """List of the names and commands that need created to launch desired
        applications."""
        return self.frozen_data.get("aliases", NotSet)

    @aliases.setter
    def aliases(self, aliases):
        self.frozen_data["aliases"] = aliases

    # Note: 'alias_mods' needs to be processed before 'environment'
    @hab_property(process_order=50)
    def alias_mods(self):
        """Dict of modifications that need to be made on aliases.
        These are used to modify the original configuration of an alias by another
        distro or config. This allows a plugin to add an environment variable to
        a specific alias even though the alias is defined by another distro/config.
        """
        return self._alias_mods

    def _load(self, filename, cached=True):
        """Sets self.filename and parses the json file returning the data."""
        ret = super()._load(filename, cached=cached)

        # Resolve the version from the various supported ways its stored.
        self._resolve_version(ret, filename)

        if not cached:
            # Ensure the version is stored on the returned dictionary
            ret["version"] = str(self.version)
        return ret

    def load(self, filename):
        # Fill in the DistroVersion specific settings before calling super
        data = self._load(filename)

        self.aliases = data.get("aliases", NotSet)
        # Store any alias_mods, they will be processed later when flattening
        self._alias_mods = data.get("alias_mods", NotSet)

        # The name should be the version == specifier.
        self.distro_name = data.get("name")
        self.name = "{}=={}".format(self.distro_name, self.version)

        data = super().load(filename, data=data)

        return data

    @hab_property()
    def version(self):
        return super().version

    @version.setter
    def version(self, version):
        # NOTE: super doesn't work for a @property.setter
        if version and not isinstance(version, Version):
            version = Version(version)
        self.frozen_data["version"] = version
