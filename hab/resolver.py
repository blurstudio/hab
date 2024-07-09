# __all__ = ["Resolver"]

import copy
import logging

import anytree
from packaging.requirements import Requirement

from . import utils
from .errors import _IgnoredVersionError
from .parsers import Config, DistroVersion, HabBase
from .site import Site
from .solvers import Solver
from .user_prefs import UserPrefs

logger = logging.getLogger(__name__)


class Resolver(object):
    """Used to resolve a hab environment setup and apply it to the current environment.

    Args:
        site (hab.Site, optional): The site configuration. if not provided, uses
            the ``HAB_PATHS`` environment variable to load the configuration.
        prereleases (bool, optional): When resolving distro versions, should
            pre-releases be included in the latest version. If not specified uses the
            value specified in site for the ``"prereleases"`` value.
        forced_requirements (list, optional): A list of additional version requirements
            to respect even if they are not specified in a config. This is provided for
            ease of hab package development and should not be used in production.
    """

    _instances = {}

    def __init__(
        self,
        site=None,
        prereleases=None,
        forced_requirements=None,
        target="hab",
    ):
        if site is None:
            site = Site()
        self.site = site

        if prereleases is None:
            prereleases = self.site.get("prereleases", False)
        self.prereleases = prereleases

        # Variables used to filter various outputs. See `hab.utils.verbosity_filter`
        # with context for more details.
        self._verbosity_target = target
        # A value of None indicates that nothing should be hidden, otherwise only
        # show the item if its min_verbosity is <= this number
        self._verbosity_value = None

        if forced_requirements:
            self.forced_requirements = Solver.simplify_requirements(forced_requirements)
        else:
            self.forced_requirements = {}
        # Store a copy of the original forced_requirements so plugins can restore
        # the original value if they need to temporarily modify it.
        self.__forced_requirements__ = copy.deepcopy(self.forced_requirements)

        logger.debug("config_paths: {}".format(self.config_paths))
        logger.debug("distro_paths: {}".format(self.distro_paths))

        self._configs = None
        self._distros = None
        self.ignored = self.site["ignored_distros"]

        # If true, then all scripts are printed instead of being written to disk
        # to allow for quick debugging of the underlying shell scripts driving hab
        # If the files are not written to disk, the calling shell scripts will
        # simply exit instead of running the requested command.
        self.dump_scripts = False

    def clear_caches(self):
        """Clears cached resolved data so it is re-generated on next use."""
        logger.debug("Resolver cache cleared.")
        self._configs = None
        self._distros = None
        self.site.cache.clear()

    def closest_config(self, path, default=False):
        """Returns the most specific leaf or the tree root matching path. Ignoring any
        path names that don't exist in self.configs.

        Args:
            path (str): A config path relative to the root of the tree.
            default (bool, optional): If True, search the default tree instead of the
                tree specified by the first name in path. The leaf nodes do not need to
                match names exactly, it will pick a default leaf that starts with the
                most common characters. Ie if path is `project_a/Sc001` it would match
                `default/Sc0` not `default/Sc01`.
        """
        if not path.startswith(HabBase.separator):
            path = "".join((HabBase.separator, path))
        # Anytree<2.9.0 had a bug when resolving URI's that end in a slash like
        # `app/` would cause a IndexError. This ensure that older versions work
        path = path.rstrip("/")

        if default:
            node_names = path.split(HabBase.separator)
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
        splits = path.split(HabBase.separator)
        # Find the forest to search for or return the default search
        root_name = splits[1 if path.startswith(HabBase.separator) else 0]
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
        return self.site["config_paths"]

    @config_paths.setter
    def config_paths(self, paths):
        # Convert string paths into a list
        if isinstance(paths, str):
            paths = utils.Platform.expand_paths(paths)

        self.site["config_paths"] = paths
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
        return self.site["distro_paths"]

    @distro_paths.setter
    def distro_paths(self, paths):
        # Convert string paths into a list
        if isinstance(paths, str):
            paths = utils.Platform.expand_paths(paths)

        self.site["distro_paths"] = paths
        # Reset _distros so we re-generate them the next time they are requested
        self._distros = None

    @property
    def distros(self):
        """A list of all of the requested distros to resolve."""
        if self._distros is None:
            self._distros = self.parse_distros(self.distro_paths)
        return self._distros

    @classmethod
    def dump_forest(
        cls,
        forest,
        attr="uri",
        fmt="{pre}{attr}",
        style=None,
        indent="  ",
        truncate=None,
    ):
        """Yields the contents of a forest to a readable string or anytree objects.

        Args:
            forest: A dictionary of hab.parser objects to dump. Common values
                are `resolver.configs`, or `resolver.distros`.
            attr (str, optional): The name of the attribute to display for each node.
                If None is passed, the anytree object is returned un-modified.
            fmt (str, optional): str.format string to control the display of
                each node in the forest. Accepts (pre, attr) keys.
            style (anytree.render.AbstractStyle, optional): Controls how anytree
                renders the branch information. If not set, defaults to a custom
                style that intents all children(recursively) to the same depth.
            indent (str, optional): The string to use for indentation. Used only
                if style is None.
            truncate (int, optional): The maximum number of results to show for
                a given tree level. If there are more child nodes than twice this
                value, only include the first and last number of these results
                with a "..." placeholder in between. Disable by passing None.
        """

        def sort_forest(items):
            """Ensures consistent sorting of the forest leaf nodes"""
            ret = utils.natural_sort(items, key=lambda item: item.name)
            if truncate and len(ret) > truncate * 2:
                # Create a anytree node that can be rendered as "..."
                placeholder = HabBase._placeholder(forest, None)
                placeholder.name = "..."
                # replace the excess middle nodes with the placeholder object
                ret = ret[:truncate] + [placeholder] + ret[-truncate:]
            return ret

        limit_pre = False
        if style is None:
            style = anytree.render.AbstractStyle(indent, indent, indent)
            limit_pre = True

        for tree_name in utils.natural_sort(forest):
            for row in anytree.RenderTree(
                forest[tree_name], style=style, childiter=sort_forest
            ):
                cfg = row.node
                # Process inheritance for this config to ensure the correct value
                cfg._collect_values(cfg, ["min_verbosity"])

                # Check if this row should be shown based on verbosity settings.
                min_verbosity = {"min_verbosity": cfg.min_verbosity}
                if not cfg.check_min_verbosity(min_verbosity):
                    # TODO: If a parent is hidden but not a child, fix rendering
                    # so the child's indent is reduced correctly.
                    continue

                # Yield the anytree node if no attr was requested
                if attr is None:
                    yield row
                else:
                    # Otherwise yield the formatted text for the node
                    pre = row.pre
                    if limit_pre:
                        pre = row.pre[: len(indent)]
                    yield fmt.format(pre=pre, attr=getattr(cfg, attr))

    def find_distro(self, requirement):
        """Returns the DistroVersion matching the requirement or None"""
        if not isinstance(requirement, Requirement):
            requirement = Requirement(requirement)

        if requirement.name in self.distros:
            app = self.distros[requirement.name]
            return app.latest_version(requirement)

    def freeze_configs(self):
        """Returns a composite dict of the freeze for all URI configs.

        Returns a dict for every non-placeholder URI where the value is the freeze
        dict of that URI. If a error is encountered when generating the freeze
        the exception subject is stored as a string instead.
        """
        out = {}
        for node in self.dump_forest(self.configs, attr=None):
            if isinstance(node.node, HabBase._placeholder):
                continue
            uri = node.node.uri
            try:
                cfg = self.resolve(uri)
            except Exception as error:
                out[uri] = f"Error resolving {uri}: {error}"
            else:
                out[uri] = cfg.freeze()
        return out

    @classmethod
    def instance(cls, name="main", **kwargs):
        """Returns a shared Resolver instance for name, initializing it if required.

        The Resolver class caches a lot of information so you only need to pay
        the price of processing a hab config once per instance. When using hab
        as an api, this lets you easily re-use the same resolver across distinct
        code paths. Be aware that **kwargs is ignored once a specific instance
        is created if you need to customize the resolver instance.

        Args:
            name (str, optional): The name of the desired instance. This allows
                you to have multiple Resolver instances with their own settings.
            **kwargs: All kwargs are passed to the Resolver initialization if
                this call needs to create the instance. Otherwise its ignored.
        """
        # Return the previously created instance if it exists
        instance = cls._instances.get(name)
        if instance:
            return instance

        # Otherwise, create a new instance, cache and return it
        logger.debug(f"Creating {cls} instance with kwargs: {kwargs}")
        instance = cls(**kwargs)
        cls._instances[name] = instance
        return instance

    def parse_configs(self, config_paths, forest=None):
        if forest is None:
            forest = {}
        for dirname, path in self.site.config_paths(config_paths):
            Config(forest, self, path, root_paths=set((dirname,)))
        return forest

    def parse_distros(self, distro_paths, forest=None):
        if forest is None:
            forest = {}
        for dirname, path in self.site.distro_paths(distro_paths):
            try:
                DistroVersion(forest, self, path, root_paths=set((dirname,)))
            except _IgnoredVersionError as error:
                logger.debug(str(error))
        return forest

    def resolve(self, uri):
        """Find the closest configuration and reduce it into its final form."""
        uri = self.uri_validate(uri)
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

        solver = Solver(requirements, self, forced=self.forced_requirements)
        return solver.resolve()

    def uri_validate(self, uri):
        """Check for issues with the provided URI and possibly modify it.

        This runs all `hab.uri.validate` entry points specified by site. These should
        point to a callable that accepts `resolver` and `uri` kwargs. If an URI
        is not valid, then an exception should be raised. The callback can update
        the URI by returning a string.
        """
        # Run any configured entry_points before aliases are calculated
        for ep in self.site.entry_points_for_group("hab.uri.validate"):
            logger.debug(f"Running hab.uri.validate entry_point: {ep}")
            func = ep.load()
            ret = func(resolver=self, uri=uri)
            if ret:
                uri = ret
        return uri

    def user_prefs(self, load=False):
        """Returns the `hab.user_prefs.UserPrefs` object for this resolver.

        Args:
            load (bool, optional): If True, calls `UserPrefs.load()` before
                returning the UserPrefs object.
        """
        try:
            self._user_prefs
        except AttributeError:
            self._user_prefs = UserPrefs(self)

        if load:
            self._user_prefs.load()
        return self._user_prefs
