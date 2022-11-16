import logging
from copy import deepcopy

from .. import NotSet
from .config import Config
from .meta import hab_property

logger = logging.getLogger(__name__)


class FlatConfig(Config):
    """A fully resolved and flattened Config object. Any values NotSet on the Config
    this is built from, are attempted to be set from the parents of that Config. If
    still not found, it will attempt to find the value from a matching config on the
    Default tree instead."""

    def __init__(self, original_node, resolver, uri=NotSet):
        super(FlatConfig, self).__init__(original_node.forest, resolver)
        self.original_node = original_node
        self.filename = original_node.filename
        self.frozen_data["context"] = original_node.context
        self._uri = uri
        # Copy the properties from the inheritance system
        self._collect_values(self.original_node)

    def _collect_values(self, node, default=False):
        logger.debug("Loading node: {} inherits: {}".format(node.name, node.inherits))
        self._missing_values = False
        # Use sort_key to ensure the properties are processed in the correct order
        for attrname in sorted(
            self._properties, key=lambda i: self._properties[i].sort_key()
        ):
            if attrname == "uri":
                # TODO: Add detection of setters to HabProperty and don't set
                # values without setters
                # There is no setter for uri, setting it now will cause errors in testing
                continue
            if getattr(self, attrname) != NotSet:
                continue
            value = getattr(node, attrname)
            if value is NotSet:
                self._missing_values = True
            else:
                setattr(self, attrname, value)
        if node.inherits and self._missing_values:
            parent = node.parent
            if parent:
                return self._collect_values(parent, default=default)
            elif not default and "default" in self.forest:
                # Start processing the default setup
                default = True
                default_node = self.resolver.closest_config(node.fullpath, default=True)
                self._collect_values(default_node, default=default)

        return self._missing_values

    @hab_property()
    def aliases(self):
        """List of the names and commands that need created to launch desired
        applications."""
        if "aliases" not in self.frozen_data:
            # Aliases are configured per version so populate them by calling this
            self.versions

        return self.frozen_data.get("aliases", {}).get(self._platform, [])

    @property
    def environment(self):
        """A resolved set of environment variables for this platform that should
        be applied to configure an environment. Any values set to None indicate
        that the variable should be unset.
        """
        if self.frozen_data.get("environment") is None:
            super(FlatConfig, self).environment
            # Add any environment variables defined by the linked versions
            for version in self.versions:
                self.merge_environment(version.environment_config, obj=version)
            # Add the HAB_URI env var for each platform so scripts know they are
            # in an activated hab environment and the original uri the user requested.
            for platform in self.resolver.site['platforms']:
                self.frozen_data.setdefault("environment", {}).setdefault(platform, {})[
                    "HAB_URI"
                ] = [self.uri]

        return self.frozen_data["environment"].get(self._platform, {})

    @property
    def fullpath(self):
        if self.context:
            return self.separator.join([name for name in self.context] + [self.name])
        return self.name

    def freeze(self):
        """Returns information that can be used to create a unfrozen copy of
        this configuration.
        """

        # ensure the version environments are flattened into the environment
        self.environment

        frozen_data = deepcopy(self.frozen_data)
        frozen_data["uri"] = self.uri
        if "versions" in self.frozen_data:
            frozen_data["versions"] = [v.name for v in self.frozen_data["versions"]]

        # Simplify the output data by removing un-needed and duplicated items
        for platform in frozen_data.get("environment", {}):
            frozen_data["environment"][platform].pop("HAB_URI", None)

        # No need to store the environment_config in a freeze
        frozen_data.pop("environment_config", None)

        # No need to store this it will always be False
        frozen_data.pop("inherits", None)

        # Remove any empty properties that are not required
        for key in ("aliases", "versions"):
            if key in frozen_data and not frozen_data[key]:
                frozen_data.pop(key, None)

        return frozen_data

    @hab_property(verbosity=1)
    def versions(self):
        if self.distros is NotSet:
            return []

        # Lazily load the contents of versions the first time it's called
        if "versions" not in self.frozen_data:
            # While processing versions, also populate aliases from the version
            platform_aliases = {}
            self.frozen_data["aliases"] = platform_aliases
            versions = []
            self.frozen_data["versions"] = versions

            reqs = self.resolver.resolve_requirements(self.distros)
            for req in reqs.values():
                version = self.resolver.find_distro(req)
                versions.append(version)

                # Populate the alias information while we are processing versions
                platforms = self.resolver.site['platforms']
                if version.aliases:
                    for platform in platforms:
                        aliases_def = version.aliases.get(platform, [])
                        aliases = [a[1] for a in aliases_def]

                        for i, alias in enumerate(aliases_def):
                            platform_aliases.setdefault(platform, {})[
                                alias[0]
                            ] = version.format_environment_value(aliases[i])

        return self.frozen_data["versions"]
