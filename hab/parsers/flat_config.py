import logging
from copy import deepcopy

from .. import NotSet, utils
from ..merge_dict import MergeDict
from .config import Config
from .meta import hab_property

logger = logging.getLogger(__name__)


class FlatConfig(Config):
    """A fully resolved and flattened Config object. Any values NotSet on the Config
    this is built from, are attempted to be set from the parents of that Config. If
    still not found, it will attempt to find the value from a matching config on the
    Default tree instead."""

    def __init__(self, original_node, resolver, uri=NotSet):
        super().__init__(original_node.forest, resolver)
        self.original_node = original_node
        self.filename = original_node.filename
        self.frozen_data["context"] = original_node.context
        self._uri = uri
        # Caches a copy of modifications that eventually need applied to aliases
        self._alias_mods = NotSet
        # Copy the properties from the inheritance system
        self._collect_values(self.original_node)
        self._finalize_values()

    def _finalize_values(self):
        """Post processing done after `_collect_values` is run."""

        # `_process_version` needs the global environment variables populated
        # so populating per-alias env var's properly inherit the global variables.
        # This call ensures that `self.frozen_data["environment"]` is populated.
        self.environment

        # Run any configured entry_points before aliases are calculated
        self.resolver.site.run_entry_points_for_group("hab.cfg.reduce.env", cfg=self)

        # Ensure distros are populated before versions get processed
        if self.distros is NotSet:
            if self.resolver.forced_requirements:
                self.distros = self.resolver.forced_requirements
            else:
                self.distros = {}

        # Process version aliases, merging global env vars.
        platform_aliases = {}
        self.frozen_data["aliases"] = platform_aliases
        for version in self.versions:
            for platform, alias, data in self._process_version(
                version, existing=platform_aliases
            ):
                platform_aliases.setdefault(platform, {})[alias] = data

        # Run any configured entry_points before finishing
        self.resolver.site.run_entry_points_for_group(
            "hab.cfg.reduce.finalize", cfg=self
        )

    def _process_version(self, version, existing=None):
        """Generator that yields each finalized alias definition dictionary
        to be stored in the frozen_data for aliases.

        Args:
            version: A Version to process.
            existing: A record of the aliases already processed. This is used
                as an early out when encountering a duplicate alias name.
                Duplicate aliases are allowed, but only uses the first encountered.

        Yields:
            tuple: 3 item tuple containing (platform, alias, alias_spec). The
                alias_spec is stored in frozen_data under the other two keys.
        """
        if not version.aliases:
            # There are no aliases to process, so we can simply exit
            return

        # TODO: Add support for the '*'' platform
        for platform in self.resolver.site["platforms"]:
            aliases_def = version.aliases.get(platform, [])
            aliases = [a[1] for a in aliases_def]

            merger = MergeDict(platforms=[platform], relative_root=version.dirname)

            for i, alias in enumerate(aliases_def):
                alias_name = alias[0]

                # Configure the merger for this version
                merger.formatter = version.format_environment_value
                merger.validator = self.check_environment

                # Only process an alias the first time it is encountered
                if existing and alias_name in existing.get(platform, {}):
                    logger.info(
                        f'Skipping duplicate alias "{alias_name}" for '
                        f'"{version.name}" on "{platform}"'
                    )
                    continue

                host_platform = utils.Platform.name()
                # Ensure the aliases are formatted and variables expanded
                data = version.format_environment_value(aliases[i])

                mods = self._alias_mods.get(alias_name, [])
                if "environment" not in data and not mods:
                    yield platform, alias_name, data
                    continue

                # Merge and flatten the alias and global env var for the platform

                # If a per-alias env var is also defined in the global env var's
                # managed by hab, use that as the base env var, otherwise overwrite
                # non-hab managed env vars as we do for global env vars.
                global_env = self.frozen_data["environment"].get(host_platform, {})
                merged_env = {}

                def extract_global_keys(operation, merged_env, global_env):
                    for plat in operation.values():
                        for key in plat:
                            if key not in merged_env and key in global_env:
                                merged_env[key] = global_env[key]

                environment = data.get("environment", {})
                extract_global_keys(environment, merged_env, global_env)
                for mod in mods:
                    env = mod.get("environment", {}).get(host_platform, {})
                    extract_global_keys(env, merged_env, global_env)

                merged_env = {platform: merged_env}

                # Update the global env vars with per-alias env vars
                merger.apply_platform_wildcards(environment, output=merged_env)
                # Apply any alias_mods specified for this alias.
                for mod in mods:
                    env = mod.get("environment")
                    if env:
                        merger.apply_platform_wildcards(env, output=merged_env)

                # Update the alias environment removing the redundant platform spec
                data["environment"] = merged_env[platform]
                yield platform, alias_name, data

    # Note: 'alias_mods' needs to be processed before 'environment'
    @hab_property(verbosity=None, process_order=50)
    def alias_mods(self):
        """Override the hab_property decorator's verbosity to hide this from the
        dump. It doesn't make sense to show this property on FlatConfig, but it's
        important to show it on the super Config class for debugging.
        """
        return super().alias_mods

    # Note: 'alias_mods' and 'distros' needs to be processed before 'environment'
    @hab_property(verbosity=2, process_order=80)
    def environment(self):
        """A resolved set of environment variables for this platform that should
        be applied to configure an environment. Any values set to None indicate
        that the variable should be unset.
        """
        if self.frozen_data.get("environment") is None:
            super().environment
            # Add any environment variables defined by the linked versions
            for version in self.versions:
                self.merge_environment(version.environment_config, obj=version)
            # Add the HAB_URI env var for each platform so scripts know they are
            # in an activated hab environment and the original uri the user requested.
            for platform in self.resolver.site["platforms"]:
                self.frozen_data.setdefault("environment", {}).setdefault(platform, {})[
                    "HAB_URI"
                ] = [self.uri]

        return self.frozen_data["environment"].get(utils.Platform.name(), {})

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
        distros = self.distros
        if distros is NotSet:
            return []
        if distros == []:
            distros = {}

        # Lazily load the contents of versions the first time it's called
        if "versions" not in self.frozen_data:
            versions = []
            if self._alias_mods is NotSet:
                self._alias_mods = {}
            self.frozen_data["versions"] = versions

            reqs = self.resolver.resolve_requirements(distros)
            for req in reqs.values():
                version = self.resolver.find_distro(req)
                versions.append(version)

                # If this version defines any alias_mods, store them for later
                if version.alias_mods:
                    # Format the alias environment at this point so any path
                    # based variables like {relative_root} are resolved against
                    # the version's directory not the alias being modified
                    mods = version.format_environment_value(version.alias_mods)
                    for name, mod in mods.items():
                        self._alias_mods.setdefault(name, []).append(mod)

        return self.frozen_data["versions"]
