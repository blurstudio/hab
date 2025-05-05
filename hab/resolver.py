# __all__ = ["Resolver"]

import concurrent.futures
import copy
import enum
import fnmatch
import logging
from contextlib import contextmanager

import anytree
from packaging.requirements import Requirement

from . import utils
from .errors import HabError, InvalidRequirementError, _IgnoredVersionError
from .parsers import Config, HabBase, StubDistroVersion
from .site import Site
from .solvers import Solver
from .user_prefs import UserPrefs

logger = logging.getLogger(__name__)


class DistroMode(enum.Enum):
    """Used by `hab.Revolver` to control which forest is used to resolve distros."""

    # TODO: Switch docstrings to `Annotated` if we move to py 3.9+ only
    # support  https://stackoverflow.com/a/78361486
    Downloaded = enum.auto()
    """Use the `downloadable_distros` forest when using `Resolver.distros`."""
    Installed = enum.auto()
    """Use the `installed_distros` forest when using `Resolver.distros`."""


class Resolver(object):
    """Used to resolve a hab environment setup and apply it to the current environment.

    Args:
        site (hab.Site, optional): The site configuration. if not provided, uses
            the ``HAB_PATHS`` environment variable to load the configuration.
        prereleases (bool, optional): When resolving distro versions, should
            pre-releases be included in the latest version. If not specified uses the
            value specified in site for the ``"prereleases"`` value.
        forced_requirements (list, optional): A list of additional distro version
            requirements to respect even if they are not specified in a config.
            This is how `optional_distros` are enabled.
            Has :py:meth:`hab.solvers.Solver.simplify_requirements` called on it.
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

        logger.debug(f"config_paths: {self.config_paths}")
        logger.debug(f"distro_paths: {self.distro_paths}")

        self._configs = None
        self.distro_mode = DistroMode.Installed
        self._downloadable_distros = None
        self._installed_distros = None
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
        self._downloadable_distros = None
        self._installed_distros = None
        self.site.cache.clear()
        [distro_finder.clear_cache() for distro_finder in self.distro_paths]

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
        """Path's used to populate `configs`."""
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

    @contextmanager
    def distro_mode_override(self, mode):
        """A context manager that sets `distro_mode` while inside the context.
        This lets you switch which distro forest is returned by the `distro` method.

        Example:

            assert resolver.distros == resolver.installed_distros
            with resolver.distro_mode_override(DistroMode.Downloaded):
                assert resolver.distros == resolver.downloadable_distros
            assert resolver.distros == resolver.installed_distros
        """
        if not isinstance(mode, DistroMode):
            raise ValueError("You can only specify DistroModes.")

        current = self.distro_mode
        logger.debug(f"Setting Resolver distro_mode to {mode} from {current}.")
        try:
            self.distro_mode = mode
            yield current
        finally:
            self.distro_mode = current
            logger.debug(f"Restored distro_mode to {self.distro_mode}.")

    @property
    def distro_paths(self):
        """`DistroFinder`s used to populate `installed_distros`."""
        return self.site["distro_paths"]

    @distro_paths.setter
    def distro_paths(self, paths):
        # Convert string paths into a list
        if isinstance(paths, str):
            paths = utils.Platform.expand_paths(paths)

        self.site["distro_paths"] = paths
        # Reset the cache so we re-generate it the next time it is requested.
        self._installed_distros = None

    @property
    def installed_distros(self):
        """A dictionary of all usable distros that have been parsed for this resolver.

        These are the distros used by hab when a hab environment is configured
        and aliases(programs) access these files.
        """
        if self._installed_distros is None:
            self._installed_distros = self.parse_distros(self.distro_paths)
        return self._installed_distros

    @property
    def distros(self):
        """A dictionary of distros for this resolver.

        This forest is used to resolve distro dependencies into config versions.

        The output is dependent on `self.distro_mode`, use the `distro_mode_override`
        context manager to change the mode temporarily.
        """
        if self.distro_mode == DistroMode.Downloaded:
            return self.downloadable_distros
        return self.installed_distros

    @property
    def downloadable_distros(self):
        """A dictionary of all distros that can be installed into `installed_distros`.

        This is used by the hab install process, not when enabling a hab
        environment. These distros are available to download and install for use
        in the `installed_distros` forest.
        """
        if self._downloadable_distros is None:
            self._downloadable_distros = self.parse_distros(
                self.site.downloads["distros"]
            )
        return self._downloadable_distros

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
                each node in the forest. Accepts (pre, attr) keys. If a callable
                is passed then it will be called passing (parser, attr=attr, pre=pre)
                and should return the text for that hab.parsers instance.
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
                parser = row.node
                # Process inheritance for this config to ensure the correct value
                parser._collect_values(parser, ["min_verbosity"])

                # Check if this row should be shown based on verbosity settings.
                min_verbosity = {"min_verbosity": parser.min_verbosity}
                if not parser.check_min_verbosity(min_verbosity):
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
                    if isinstance(fmt, str):
                        yield fmt.format(pre=pre, attr=getattr(parser, attr))
                    else:
                        yield fmt(parser, attr=attr, pre=pre)

    def find_distro(self, requirement):
        """Returns the DistroVersion matching the requirement.

        Raises:
            InvalidRequirementError: Raised if no DistroVersion's could be found
                matching the requirement.
        """
        if not isinstance(requirement, Requirement):
            requirement = Requirement(requirement)

        if requirement.name in self.distros:
            distro = self.distros[requirement.name]
            return distro.latest_version(requirement)

        # If allowed to, create a stub version instead of raising a error
        stub = self.get_stub_distro(requirement)
        if stub:
            return stub

        raise InvalidRequirementError(
            f"Unable to find a distro for requirement: {requirement}"
        ) from None

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

    def get_stub_distro(self, requirement: Requirement):
        """Returns the `StubDistroVersion` instance for requirement if allowed.

        If the site settings allow the requirement to be a stub, returns the
        instance of the stub, creating it if required.
        """

        name = requirement.name
        if name in self.distros:
            # Return the existing StubDistroVersion if already created
            stub = self.distros[name].stub
            if stub:
                return stub

        # Check to see if name matches any of the stub_distros
        for stub_name, stub_rule in self.site["stub_distros"].items():
            matches = fnmatch.fnmatchcase(name, stub_name)
            if not matches:
                continue
            # If the stub rule is set to None, its unset, do not create a stub
            if stub_rule is None:
                continue

            # If a limit is defined only allow the stub if the requirement is
            # contained inside the limit.
            if "limit" in stub_rule:
                if not utils.specifier_valid(requirement.specifier, stub_rule["limit"]):
                    continue
            break
        else:
            # No stub rule applies, do not create a stub
            return

        logger.info(
            f"Creating StubDistroVersion: {name} from stub_distros: {stub_name}"
        )
        # NOTE: This mutates self.distros by adding the stub to it. You can undo
        # this by calling `Distro.stub = None`.
        stub = StubDistroVersion(self.distros, self, name=name)
        # Store the stub on the Distro for future calls
        self.distros[name].stub = stub
        return stub

    def install(
        self,
        uris=None,
        additional_distros=None,
        target=None,
        dry_run=True,
        replace=False,
    ):
        """Ensure the required distros are installed for use in hab.

        Resolves the distros defined by one or more URI's and additional distros
        against the distro versions available on from a `downloadable_distros`.
        Then extracts them into a target location for use in hab environments.

        Each URI and additional_distros requirement is resolved independently. This
        allows you to install multiple versions of a given distro so the correct
        one is available when a given URI is used in a hab environment.

        Args:
            uris (list, optional): A list of URI strings. These URI's are resolved
                against the available distros in `downloadable_distros`.
            additional_distros (list, optional): A list of additional distro
                requirements to resolve and install.
            target (os.PathLike, optional): The target directory to install all
                resolved distros into. This is the root directory. The per-distro
                name and version paths are added relative to this directory based
                on the `site.downloads["relative_path"]` setting.
            dry_run (bool, optional): If True then don't actually install the
                the distros. The returned list is the final list of all distros
                that need to be installed.
            replace (bool, optional): This method skips installing any distros
                that are already installed. Setting this to True will delete the
                existing distros before re-installing them.

        Returns:
            list: A list of DistroVersion's that were installed. The distros are
                from `downloadable_distros` and represent the remote resources.
        """

        def str_distros(distros, sep=", "):
            return sep.join([d.name for d in missing])

        if target is None:
            target = self.site.downloads.get("install_root")
            if target is None:
                raise HabError(
                    'You must specify target, or set ["downloads"]["install_root"] '
                    "in your site config."
                )

        distros = set()
        if uris is None:
            uris = []
        # Resolve all distros and any additional distros they may require from
        # the download forest.
        with self.distro_mode_override(DistroMode.Downloaded):
            if additional_distros:
                requirements = self.resolve_requirements(additional_distros)
                for req in requirements.values():
                    version = self.find_distro(req)
                    distros.add(version)

            for uri in uris:
                cfg = self.resolve(uri)
                distros.update(cfg.versions)

        # Check the installed forest for any that are not already installed and
        # build a list of missing distros.
        missing = []
        for distro in distros:
            if replace:
                missing.append(distro)
                continue

            try:
                installed = self.find_distro(distro.name)
            except InvalidRequirementError:
                installed = []
            if not installed:
                missing.append(distro)

        # To ensure consistent logging and processing, sort missing items
        missing = sorted(missing, key=lambda i: i.name)

        if dry_run:
            logger.warning(f"Dry Run would install distros: {str_distros(missing)}")
            return missing

        # Download and install the missing distros using threading to speed up
        # the download process.
        logger.warning(f"Installing distros: {str_distros(missing)}")
        with concurrent.futures.ThreadPoolExecutor() as executor:
            for distro in missing:
                logger.warning(f"Installing distro: {distro.name}")
                executor.submit(distro.install, target, replace=replace)
        logger.warning(f"Installed distros: {str_distros(missing)}")
        return missing

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

    def parse_distros(self, distro_finders, forest=None):
        """Parse all provided DistroFinders and populate the forest of distros."""
        if forest is None:
            forest = {}
        for distro_finder in distro_finders:
            for _, path, _ in distro_finder.distro_path_info():
                try:
                    distro_finder.distro(forest, self, path)
                except _IgnoredVersionError as error:
                    logger.debug(str(error))
        return forest

    def resolve(self, uri, forced_requirements=None):
        """Find the closest configuration and reduce it into its final form.

        Args:
            uri (str): The URI to resolve.
            forced_requirements (list, optional): A list of additional distro version
                requirements to respect even if they are not specified in a config.
                Has :py:meth:`hab.solvers.Solver.simplify_requirements` called on it.
        """
        uri = self.uri_validate(uri)
        context = self.closest_config(uri)
        try:
            # Apply the custom forced_requirements if provided
            if forced_requirements is not None:
                current = self.forced_requirements

                self.forced_requirements = Solver.simplify_requirements(
                    forced_requirements
                )
                logger.warning(f"Forced Requirements overridden: {forced_requirements}")

            return context.reduced(self, uri=uri)
        finally:
            # Ensure the forced_requirements are restored no matter what.
            if forced_requirements is not None:
                self.forced_requirements = current

    def resolve_requirements(self, requirements, omittable=None):
        """Recursively solve the provided requirements into a final list of requirements.

        Args:
            requirements (list): The requirements to resolve.
            omittable (list, optional): A list of distro names that are not required.
                If a suitable distro can not be found, normally an `InvalidRequirementError`
                is raised. If that distro name is in this list a warning is logged instead.

        Raises:
            MaxRedirectError: Redirect limit reached, unable to resolve the requested
                requirements.
        """

        if isinstance(requirements, list):
            requirements = Solver.simplify_requirements(requirements)

        solver = Solver(
            requirements, self, forced=self.forced_requirements, omittable=omittable
        )
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
