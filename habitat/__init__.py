from __future__ import print_function
import anytree
import glob
import logging
import os
from .parsers import Config, HabitatBase, ApplicationVersion
from .solvers import Solver
from packaging.requirements import Requirement
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
        if not path.startswith(HabitatBase.separator):
            path = "".join((HabitatBase.separator, path))
        if default:
            node_names = path.split(HabitatBase.separator)
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
        splits = path.split(HabitatBase.separator)
        # Find the forest to search for or return the default search
        root_name = splits[1 if path.startswith(HabitatBase.separator) else 0]
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
        # Convert string paths into a list
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
        # Convert string paths into a list
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
        for tree_name in sorted(forest):
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

    def parse_configs(self, config_paths, forest=None):
        if forest is None:
            forest = {}
        for dirname in config_paths:
            for path in sorted(glob.glob(os.path.join(dirname, "*.json"))):
                Config(forest, self, path, root_paths=set((dirname,)))
        return forest

    def parse_distros(self, distro_paths, forest=None):
        if forest is None:
            forest = {}
        for dirname in distro_paths:
            for path in sorted(glob.glob(os.path.join(dirname, "*", ".habitat.json"))):
                ApplicationVersion(forest, self, path, root_paths=set((dirname,)))
        return forest

    def resolve(self, uri):
        context = self.closest_config(uri)
        return context.reduced(self, uri=uri)

    def resolve_requirements(self, requirements):
        """Recursively solve the provided requirements into a final list of requirements.

        Args:
            requirements (list): The requirements to resolve.

        Raises:
            MaxRedirectError: Redirect limit reached, unable to resolve the requested
                requirements.
        """

        solver = Solver(requirements, self)
        return solver.resolve()
