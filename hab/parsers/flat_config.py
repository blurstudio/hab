import logging

from .config import Config
from .meta import NotSet, hab_property

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
        self._context = original_node.context
        self._uri = uri
        self._versions = None
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
                default_node = self.resolver.closest_config(node.fullpath)
                self._collect_values(default_node, default=default)

        return self._missing_values

    @hab_property()
    def aliases(self):
        """List of the names and commands that need created to launch desired
        applications."""
        ret = {}
        for version in self.versions:
            if version.aliases:
                aliases_def = version.aliases.get(self._platform, [])
                aliases = [a[1] for a in aliases_def]

                for i, alias in enumerate(aliases_def):
                    ret[alias[0]] = version.format_environment_value(aliases[i])

        return ret

    @property
    def environment(self):
        """A resolved set of environment variables that should be applied to
        configure an environment. Any values containing a empty string indicate
        that the variable should be unset.
        """
        empty = self._environment is None
        super(FlatConfig, self).environment
        # Add any environment variables defined by the linked versions
        if empty:
            for version in self.versions:
                self.update_environment(version.environment_config, obj=version)

        return self._environment

    @property
    def fullpath(self):
        return self.separator.join([name for name in self.context] + [self.name])

    @hab_property(verbosity=1)
    def versions(self):
        if self._distros is NotSet:
            return []

        if self._versions is None:
            self._versions = []
            reqs = self.resolver.resolve_requirements(self.distros)
            for req in reqs.values():
                self._versions.append(self.resolver.find_distro(req))

        return self._versions
