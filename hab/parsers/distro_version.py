from packaging.version import InvalidVersion, Version

from ..errors import _IgnoredVersionError
from .distro import Distro
from .hab_base import HabBase
from .meta import NotSet, hab_property


class DistroVersion(HabBase):
    """A specific version of the loaded `Distro`'s. Including its requirements,
    aliases and environment variables."""

    _context_method = "name"
    _placeholder = Distro

    def _init_variables(self):
        super(DistroVersion, self)._init_variables()
        self.aliases = NotSet

    @hab_property()
    def aliases(self):
        """List of the names and commands that need created to launch desired
        applications."""
        return self._aliases

    @aliases.setter
    def aliases(self, aliases):
        self._aliases = aliases

    def load(self, filename):
        # Fill in the DistroVersion specific settings before calling super
        data = self._load(filename)
        self.aliases = data.get("aliases", NotSet)

        # The version can be stored in several ways to make deployment and dev easier
        version_txt = self.dirname / ".hab_version.txt"
        if "version" in data:
            self.version = data["version"]
        elif version_txt.exists():
            self.version = version_txt.open().read().strip()
        else:
            # If version is not defined in json data extract it from the parent
            # directory name. This allows for simpler distribution without needing
            # to modify version controlled files.
            try:
                self.version = self.dirname.name
            except InvalidVersion:
                """The parent directory was not a valid version, attempt to get a
                version using setuptools_scm.
                """
                from setuptools_scm import get_version

                try:
                    self.version = get_version(
                        root=self.dirname, version_scheme="release-branch-semver"
                    )
                except LookupError:
                    if self.dirname.name in self.resolver.ignored:
                        # This object is not added to the forest until super is called
                        raise _IgnoredVersionError(
                            'Skipping "{}" its dirname is in the ignored list.'.format(
                                filename
                            )
                        ) from None
                    raise LookupError(
                        'Hab was unable to determine the version for "{filename}".\n'
                        "The version is defined in one of several ways checked in this order:\n"
                        "1. The version property in `.hab.json`.\n"
                        "2. A `.hab_version.txt` file next to `.hab.json`.\n"
                        "3. `.hab.json`'s parent directory name.\n"
                        "4. setuptools_scm can get a version from version control.\n"
                        "The preferred method is #3 for deployed releases. #4 is the "
                        "preferred method for developers working copies.".format(
                            filename=self.filename
                        )
                    ) from None

        # The name should be the version == specifier.
        self.distro_name = data.get("name")
        self.name = u"{}=={}".format(self.distro_name, self.version)

        data = super(DistroVersion, self).load(filename, data=data)

        return data

    @hab_property()
    def version(self):
        return super(DistroVersion, self).version

    @version.setter
    def version(self, version):
        # NOTE: super doesn't work for a @property.setter
        if version and not isinstance(version, Version):
            version = Version(version)
        self._version = version
