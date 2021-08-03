from __future__ import print_function
import anytree
import json
import glob
import logging
import os
from .errors import DistroNotDefined, NoValidVersion
from .parsers import Config, ApplicationVersion
from .solvers import Solver
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
            config_paths
            if config_paths
            else os.getenv("HAB_CONFIG_PATHS", "").split(os.pathsep)
        )
        self.distro_paths = (
            distro_paths
            if distro_paths
            else os.getenv("HAB_DISTRO_PATHS", "").split(os.pathsep)
        )
        logger.debug("config_paths: {}".format(self.config_paths))
        logger.debug("distro_paths: {}".format(self.distro_paths))
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

    def closest_config(self, path, default=False):
        """Returns the most specific leaf or the tree root matching path. Ignoring any
        path names that don't exist in self.configs.

        Args:
            path (str): A config path relative to the root of the tree.
            default (bool, optional): If True, search the default tree instead of the
                tree specified by the first name in path. The leaf nodes do not need to
                match names exactly, it will pick a default leaf that starts with the
                most common characters. Ie if path is `:project_a:Sc001` it would match
                `:default:Sc0` not `:default:Sc01`.
        """
        if default:
            node_names = path.split(":")
            current = self.configs["default"]
            # Skip the root and project name it won't match default
            for node_name in node_names[2:]:
                # Find the node that starts with the longest match
                matches = sorted(
                    [c for c in current.children if node_name.startswith(c.name)],
                    key=lambda i: i.name,
                    reverse=True,
                )
                if matches:
                    current = matches[0]
                else:
                    break
            return current

        # Handle the non-default lookup
        splits = path.split(":")
        # Find the forest to search for or return the default search
        root_name = splits[1 if path.startswith(":") else 0]
        if root_name not in self.configs:
            return self.closest_config(path, default=True)

        resolver = anytree.Resolver()
        try:
            # Workaround a zombie bug in anytree's glob. Where glob doesn't match
            # top level paths and will raise a IndexError incorrectly.
            # https://github.com/c0fec0de/anytree/issues/125
            if len(splits) > 2:
                items = resolver.glob(self.configs[root_name], path)
            else:
                return resolver.get(self.configs[root_name], path)
        except anytree.resolver.ResolverError as e:
            return e.node
        if items:
            return items[0]
        # TODO: If the anytree bug gets fixed we should start hitting this line.
        # Until then exclude it from the completeness check.
        return self.configs[root_name]  # pragma: no cover

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

    @classmethod
    def dump_forest(cls, forest, style=None):
        """Convert a forest dictionary to a readable string"""
        if style is None:
            style = anytree.render.AsciiStyle()
        ret = []
        for tree_name in forest:
            ret.append(tree_name)
            tree = str(anytree.RenderTree(forest[tree_name], style))
            for line in tree.split("\n"):
                ret.append("    {}".format(line))
        return "\n".join(ret)

    def find_distro(self, requirement):
        """Returns the ApplicationVersion matching the requirement or None"""
        if not isinstance(requirement, Requirement):
            requirement = Requirement(requirement)
        if requirement.name in self.distros:
            app = self.distros[requirement.name]
            return app.latest_version(requirement)

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

    def parse_configs(self, config_paths, forest=None):
        if forest is None:
            forest = {}
        for dirname in config_paths:
            for path in sorted(glob.glob(os.path.join(dirname, "*.json"))):
                Config(forest, self, path)
        return forest

    def parse_distros(self, distro_paths, forest=None):
        if forest is None:
            forest = {}
        for dirname in distro_paths:
            for path in sorted(glob.glob(os.path.join(dirname, "*", ".habitat.json"))):
                ApplicationVersion(forest, self, path)
        return forest

    @classmethod
    def parse_distros_old(cls, distro_paths, relative=True):
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

    def resolve(self, uri):
        context = self.closest_config(uri)
        return context.reduced(self, uri=uri)

    def resolve_environment(self, context):
        for app in context.get("apps", []):
            req = Requirement(app)
            if req.name not in self.distros:
                raise DistroNotDefined(
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
                # TODO: Define a better exception for this.
                raise NoValidVersion(
                    'Unable to find a valid version for "{}" requirement'.format(req)
                )

            logger.info("Using {} {}".format(req.name, version))

    def resolve_requirements(self, requirements):
        """Recursively solve the provided requirements into a final list of requirements.

        Args:
            requirements (list): The requirements to resolve.

        Raises:
            Exception: "Exceeded maximum depth" if no results were found
            Exception: "Unable to find a valid version for ..."
        """

        solver = Solver(requirements, self)
        return solver.resolve()

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


r"""
set HAB_CONFIG_PATHS=C:\blur\dev\habitat\tests\configs\*
set HAB_DISTRO_PATHS=C:\blur\dev\habitat\tests\distros\*


import logging; logging.basicConfig(level=logging.DEBUG)
from habitat import Resolver
r=Resolver()
cfg = r.closest_config(':project_a:Sc001')
print(cfg.dump())

python -c "import logging; logging.basicConfig(level=logging.DEBUG);from habitat import Resolver;r=Resolver();cfg = r.closest_config(':project_a:Sc001');print(cfg.dump())"
"""
