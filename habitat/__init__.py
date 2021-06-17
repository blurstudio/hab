from __future__ import print_function
import json
import glob
import logging
import os
from packaging.requirements import Requirement
from packaging.version import Version
from future.utils import string_types


logger = logging.getLogger(__name__)


class Resolver(object):
    """
    Configs: A configuration of requested environment setups. Can cover multiple contexts
    Context: A string or list that is used to choose the config's to use.
    Config: Configs reduced to just the configs that match the context and flattened
        into a single simplified config.
    """

    def __init__(self, config_paths=None, distro_paths=None):
        self.config_paths = (
            config_paths if config_paths else os.getenv("HAB_CONFIG_PATHS", "")
        )
        self.distro_paths = (
            distro_paths if distro_paths else os.getenv("HAB_DISTRO_PATHS", "")
        )
        self._configs = None
        self._distros = None

    @classmethod
    def absolute_path(cls, path, root):
        """Return the absolute path for root.

        Args:
            path (str): The string to convert to a absolute path.
            root (str): If path is relative use this as directory the root path.
        """
        return os.path.abspath(os.path.join(root, path))

    @property
    def config_paths(self):
        return self._config_paths

    @config_paths.setter
    def config_paths(self, paths):
        if isinstance(paths, string_types):
            paths = paths.split(os.pathsep)
        self._config_paths = paths
        # Reset _configs so we re-generate them the next time they are requested
        self._configs = None

    @property
    def configs(self):
        """A dictionary of all configurations that have been parsed for this resolver"""
        if self._configs is None:
            self._configs = self.parse_configs(self.config_paths)
        return self._configs

    @property
    def distro_paths(self):
        return self._distro_paths

    @distro_paths.setter
    def distro_paths(self, paths):
        if isinstance(paths, string_types):
            paths = paths.split(os.pathsep)
        self._distro_paths = paths
        # Reset _distros so we re-generate them the next time they are requested
        self._distros = None

    @property
    def distros(self):
        if self._distros is None:
            self._distros = self.parse_distros(self.distro_paths)
        return self._distros

    def find_distro(self, name):
        pass

    @classmethod
    def format(cls, value, config):
        """Generate a keyword dictionary from the config used to format value.

        Args:
            value (str): The string to call format on.
            config (dict): A config dictionary to build the format kwargs with.

        Returns:
            str: The formatted value
        """
        kwargs = {}
        kwargs.update(config.get("variables", {}))
        kwargs["relative"] = os.path.dirname(config["filename"])
        return value.format(**kwargs)

    @classmethod
    def parse_configs(cls, config_paths):
        contexts = {}
        for dirname in config_paths:
            for path in sorted(glob.glob(os.path.join(dirname, "*.json"))):
                with open(path) as fle:
                    config = json.load(fle)
                # Make a copy of the context so we can add root to it
                context = list(config["context"])
                # Add the default root context object
                context.insert(0, "root")
                working_context = contexts
                for key in context:
                    working_context = working_context.setdefault(key, {})
                working_context.setdefault("configs", []).append(config)
        # The root dictionary was just used to make it easier to construct the
        # dictionary recursively remove it
        return contexts["root"]

    @classmethod
    def parse_distros(cls, distro_paths, relative=True):
        distros = {}
        for dirname in distro_paths:
            # Allow directly passing a git checkout path
            wip = os.path.join(dirname, ".habitat.json")
            if os.path.exists(wip):
                paths = (wip,)
                logger.debug("Config Loading: {}".format(wip))
                develop = True
            else:
                # List only directories by using glob
                glob_str = os.path.join(dirname, "*", "*", ".habitat.json")
                paths = sorted(glob.glob(glob_str))
                logger.debug("Config Finding: {}".format(glob_str))
                develop = False

            for path in paths:
                root = os.path.dirname(path)
                logger.debug("Parsing: {}".format(path))
                with open(path) as fle:
                    config = json.load(fle)
                config["filename"] = path
                if develop:
                    config["version"] = "DEVELOPER"
                else:
                    # If version is not defined use the version folder name.
                    # TODO: Is this a good idea?
                    if "version" not in config:
                        config["version"] = Version(os.path.basename(root))

                # TODO: move this to the resolved step
                if not relative:
                    # For supported fields convert lines starting with a `.` to
                    # absolute paths relative to path
                    for cfg in config.get("environment").values():
                        value = cfg["value"]
                        if not isinstance(value, list):
                            # We allow the json to store a string or list, but
                            # internally we will expect a list for value
                            value = [value]
                        # Convert any relative paths to absolute paths relative to the
                        # original .json file
                        modified = []
                        for v in value:
                            modified.append(cls.format(v, config))
                            # modified.append(cls.absolute_path(root, v))
                        cfg["value"] = modified

                distros.setdefault(config["name"], {})[config["version"]] = config
                # config.get("requires")
        return distros

    @classmethod
    def reduce_context(cls, contexts):
        """Reduces the contexts down to a single config"""
        if len(contexts) == 1:
            # Only one context was provided its already reduced
            return contexts[0]
        resolved = {}
        for context in contexts:
            for key, value in context.items():
                if key == "apps":
                    apps = resolved.setdefault(key, {})
                    for app, reqs in context[key].items():
                        # TODO: Support app version specifiers like houdini18.5>=18.5.123
                        for requirement in reqs:
                            logger.debug("{} [{}]".format(app, requirement))
                            req = Requirement(requirement)
                            app_map = apps.setdefault(app, [])
                            existing = [Requirement(r).name for r in app_map]
                            logger.debug(
                                "Name: {} EXISTING: {}".format(req.name, existing)
                            )
                            try:
                                index = existing.index(req.name)
                            except ValueError:
                                app_map.append(requirement)
                            else:
                                # Replace the existing requirement with the new one
                                app_map[index] = requirement
                else:
                    # We don't need to iterate into the other values just
                    # set them, replacing any existing values
                    resolved[key] = value
        return resolved

    def resolve(self, context):
        contexts = self.resolve_contexts(context, self.configs)
        return self.reduce_context(contexts)

    def resolve_environment(self, context):
        for app in context.get("apps", []):
            req = Requirement(app)
            if req.name not in self.distros:
                raise ValueError(
                    "Unable to find app definition for {}".format(req.name)
                )
            logger.debug("Found application: {}".format(req))
            versions = self.distros[req.name].keys()
            versions = req.specifier.filter(versions)
            if logger.isEnabledFor(logging.DEBUG):
                # Only convert versions to a list if we are going to log it
                versions = list(versions)
            logger.debug("Valid Versions: {}".format(versions))

            try:
                version = max(versions)
            except ValueError:
                raise Exception('Unable to find a valid version for "{}"'.format(req))

            logger.info("Using {} {}".format(req.name, version))

    @classmethod
    def resolve_contexts(cls, selected_context, context_map):
        """Removes all configs that are not directly referenced by the context"""
        contexts = []
        if selected_context:
            relative = context_map
            for key in selected_context:
                if key not in relative:
                    # Nothing left to parse exit early
                    logger.debug("breaking early on: {}".format(key))
                    break
                relative = relative[key]
                for config in relative.get("configs", []):
                    if not config.get("inherits", True):
                        # This config doesn't inherit from the parents, remove them.
                        contexts = [config]
                    else:
                        contexts.append(config)
        else:
            # Empty context provided
            logger.debug("No context provided")
            contexts = context_map["configs"]
        return contexts


# set HABITAT_CONFIG_PATHS=H:\public\mikeh\simp\habitat_cfgs\config;H:\public\mikeh\simp\habitat_cfgs\config\projectDummy
# set HABITAT_DISTRO_PATHS=H:\public\mikeh\simp\habitat_cfgs\distro;C:\blur\dev\dcc\maya\tikal

# cls && python -c "import json, logging; logging.basicConfig(level=logging.DEBUG);from habitat.habitat import Resolver; r= Resolver(); print(json.dumps(r.distros, indent=2))"
# cls && python -c "import json, logging; logging.basicConfig(level=logging.DEBUG);from habitat.habitat import Resolver; r= Resolver(); print(r.resolve_environment(r.resolve(['projectDummy', 'Sc001', 'S0001.00'])))"
