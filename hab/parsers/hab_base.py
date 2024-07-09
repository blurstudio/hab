import logging
import os
import subprocess
from pathlib import Path

import anytree
from colorama import Fore, Style
from jinja2 import Environment, FileSystemLoader
from packaging.version import Version

from .. import NotSet, utils
from ..errors import (
    DuplicateJsonError,
    HabError,
    InvalidAliasError,
    ReservedVariableNameError,
)
from ..formatter import Formatter
from ..site import MergeDict
from ..solvers import Solver
from .meta import HabMeta, hab_property

logger = logging.getLogger(__name__)

TEMPLATES = Path(__file__).parent.parent / "templates"


class HabBase(anytree.NodeMixin, metaclass=HabMeta):
    """Base class for the various parser classes. Provides most of the functionality
    to parse a json configuration file and resolve it for use in hab.

    Args:
        forest (dict): A dictionary map used to calculate the context when resolving
            this object.
        resolver (hab.Resolver): The Resolver used to lookup requirements.
        filename (str, optional): Automatically call load on this filename.
        parent (hab.parsers.HabBase, optional): Parent for this object.
        root_paths (set, optional): The base glob path being processed to create the
            HabBase objects for this forest. If two
    """

    # Subclasses can change this to control how data is tweaked by the load method.
    _context_method = "key"
    # A instance of this class is used to build a parent anytree item if no
    # configuration was processed yet to fill in that node. This is set to the
    # Placeholder class after it is defined below. This allows the
    # DistroVersion class to use Distro as its placeholder
    _placeholder = None

    def __init__(self, forest, resolver, filename=None, parent=None, root_paths=None):
        super().__init__()
        self.frozen_data = {}
        self._filename = None
        self._dirname = None
        self._distros = NotSet
        self._variables = NotSet
        self._uri = NotSet
        self.parent = parent
        self.root_paths = set()
        if root_paths:
            self.root_paths = root_paths
        self.forest = forest
        self.resolver = resolver
        if filename:
            self.load(filename)

    def __repr__(self):
        cls = type(self)
        return "{}.{}('{}')".format(cls.__module__, cls.__name__, self.fullpath)

    def _cache(self):
        return {}

    def _collect_values(self, node, props=None, default=False):
        """Recursively process this config node and its parents until all
        missing_values have been resolved or we run out of parents.

        Args:
            node (HabBase): This node's values are copied to self as long as
                they are not NotSet.
            props (list, optional): The props to process, if None is
                passed then uses `hab_property` values respecting sort_key.
            default (bool, optional): Enables processing the default nodes as
                part of this methods recursion. Used for internal tracking.
        """
        logger.debug("Loading node: {} inherits: {}".format(node.name, node.inherits))
        if props is None:
            props = sorted(
                self._properties, key=lambda i: self._properties[i].sort_key()
            )

        self._missing_values = False
        # Use sort_key to ensure the props are processed in the correct order
        for attrname in props:
            if getattr(self, attrname) != NotSet:
                continue
            if attrname == "alias_mods":
                if hasattr(node, "alias_mods") and node.alias_mods:
                    self._alias_mods = {}
                    # Format the alias environment at this point so any path
                    # based variables like {relative_root} are resolved against
                    # the node's directory not the alias being modified
                    mods = node.format_environment_value(node.alias_mods)
                    for name, mod in mods.items():
                        self._alias_mods.setdefault(name, []).append(mod)
                continue
            value = getattr(node, attrname)
            if value is NotSet:
                self._missing_values = True
            else:
                setattr(self, attrname, value)

        if node.inherits and self._missing_values:
            parent = node.parent
            if parent:
                return self._collect_values(parent, props=props, default=default)
            elif not default and "default" in self.forest:
                # Start processing the default setup
                default = True
                default_node = self.resolver.closest_config(node.fullpath, default=True)
                self._collect_values(default_node, props=props, default=default)

        return self._missing_values

    @classmethod
    def _dump_versions(cls, value, verbosity=0, color=None):
        """Returns the version information for this object as a list of strings."""
        if verbosity < 3:
            # Only show the names of the versions
            return sorted([v.name for v in value], key=lambda i: i.lower())

        # Include the definition of the version's path for debugging
        if color:  # pragma: no cover
            fmt = f"{Fore.GREEN}{{}}{Style.RESET_ALL}:  {{}}"
        else:
            fmt = "{}:  {}"
        return [
            fmt.format(v.name, v.filename)
            for v in sorted(value, key=lambda i: i.name.lower())
        ]

    def check_environment(self, environment_config):
        """Check that the environment config only makes valid adjustments.
        For example, check that we never replace path, only append/prepend are allowed.
        """
        for operation in ("unset", "set", "prepend", "append"):
            if operation not in environment_config:
                continue

            keys = environment_config.get(operation, [])
            if operation == "set":
                # set is a dictionary while unset is a list
                keys = keys.keys()

            for key in keys:
                key_upper = key.upper()

                # These are reserved environment variables that can not be configured
                # by configs and distros.
                if key_upper == "HAB_URI":
                    raise KeyError(f'"{key_upper}" is a reserved environment variable')

                # We can't clear "PATH" or it would likely break the shell and
                # application execution.
                if key_upper == "PATH":
                    msg = None
                    if operation == "set":
                        key = environment_config[operation][key]
                        msg = 'You can not use PATH for the set operation: "{}"'
                    elif operation == "unset":
                        msg = "You can not unset PATH"
                    if msg:
                        raise ValueError(msg.format(key))

    def check_min_verbosity(self, config):
        """Return if the given config should be visible based on the resolver's
        current verbosity settings. Returns True if there isn't a resolver.
        """
        if not self.resolver:
            return True

        # Respect `hab.utils.verbosity_filter` with context settings
        target = self.resolver._verbosity_target
        current = self.resolver._verbosity_value

        if current is None:
            # If None, always show all results
            return True

        min_verbosity = self.get_min_verbosity(config, target)
        return current >= min_verbosity

    @property
    def context(self):
        """A list of parent context strings.

        The resolved URI parents of the this object. This does not include the name
        of the object, only its parents. `project_a/Sc001` would resolve into context:
        `["project_a"]` and name: `"Sc001"`.
        """
        return self.frozen_data.get("context", NotSet)

    @context.setter
    def context(self, context):
        self.frozen_data["context"] = context

        if not self.context:
            # Add the root of this tree to the forest
            if self.name in self.forest:
                if not isinstance(self.forest[self.name], self._placeholder):
                    msg = 'Can not add "{}", the context "{}" it is already set'.format(
                        self.filename,
                        self.fullpath,
                    )
                    if self.forest[self.name].root_paths.intersection(self.root_paths):
                        # If one of the root_paths was already added to target, then
                        # the same context was defined inside a folder structure.
                        # We  only support this from unique config/distro paths like if
                        # a developer is overriding a new version of a config.
                        raise DuplicateJsonError(msg)
                    else:
                        logger.warning(msg)
                        # Document that we have processed the new paths so if there are
                        # any duplicate context:name defined in these paths, the above
                        # exception is raised.
                        self.forest[self.name].root_paths.update(self.root_paths)

                        # Do not run the rest of this method
                        return

                # Preserve the children of the placeholder object if it exists
                self.children = self.forest[self.name].children
            self.forest[self.name] = self
            logger.debug("Add to forest: {}".format(self))
        else:
            resolver = anytree.Resolver("name")
            # Get the tree root
            root_name = self.context[0]
            if root_name in self.forest:
                root = self.forest[root_name]
                logger.debug("Using root: {}".format(root.fullpath))
            else:
                root = self._placeholder(self.forest, self.resolver)
                root.name = root_name
                self.forest[root_name] = root
                logger.debug("Created placeholder root: {}".format(root.fullpath))

            # Process the intermediate parents
            for child_name in self.context[1:]:
                try:
                    root = resolver.get(root, child_name)
                    logger.debug("Found intermediary: {}".format(root.fullpath))
                except anytree.resolver.ResolverError:
                    root = self._placeholder(self.forest, self.resolver, parent=root)
                    root.name = child_name
                    logger.debug(
                        "Created placeholder intermediary: {}".format(root.fullpath)
                    )

            # Add this node to the tree
            try:
                target = resolver.get(root, self.name)
            except anytree.resolver.ResolverError:
                # There is no placeholder, just add self as a child
                self.parent = root
                logger.debug("Adding to parent: {}".format(root.fullpath))
            else:
                if isinstance(target, self._placeholder) and target.name == self.name:
                    # replace the placeholder with self
                    self.parent = target.parent
                    self.children = target.children
                    # Remove the placeholder from the tree
                    target.parent = None
                    logger.debug("Removing placeholder: {}".format(target.fullpath))
                else:
                    msg = 'Can not add "{}", the context "{}" it is already set'.format(
                        self.filename,
                        self.fullpath,
                    )
                    if target.root_paths.intersection(self.root_paths):
                        # If one of the root_paths was already added to target, then
                        # the same context was defined inside a folder structure.
                        # We  only support this from unique config/distro paths like if
                        # a developer is overriding a new version of a config.
                        raise DuplicateJsonError(msg)
                    else:
                        logger.warning(msg)

                        # Document that we have processed the new paths so if there are
                        # any duplicate context:name defined in these paths, the above
                        # exception is raised.
                        target.root_paths.update(self.root_paths)
                        # Do not run the rest of this method
                        return

    @property
    def dirname(self):
        """The directory name of `self.filename`. This value is used to by
        `self.format_environment_value` to fill the "relative_root" variable.
        """
        return self._dirname

    # Note: 'distros' needs to be processed before 'environment'
    @hab_property(verbosity=3, process_order=50)
    def distros(self):
        """A list of all of the requested distros to resolve."""
        return self._distros

    @distros.setter
    def distros(self, distros):
        # Ensure the contents are converted to Requirement objects
        if distros:
            distros = Solver.simplify_requirements(distros)
        self._distros = distros

    def dump(self, environment=True, environment_config=False, verbosity=0, color=None):
        """Return a string of the properties and their values.

        Args:
            environment (bool, optional): Show the environment value.
            environment_config (bool, optional): Show the environment_config value.
            verbosity (int, optional): More information is shown with higher values.
            color (bool, optional): Add console colorization to output. If None,
                respect the site property "colorize" defaulting to True.

        Returns:
            str: The configuration converted to a string
        """
        if color is None:  # pragma: no cover
            color = self.resolver.site.get("colorize", True)

        ret = []
        # Update what properties are shown in the dump
        props = self._properties.copy()
        for k, v in (
            ("environment", environment),
            ("environment_config", environment_config),
        ):
            if not v:
                del props[k]

        for prop in sorted(props, key=lambda p: (props[p].group, p)):
            # Ignore any props with higher verbosity than requested
            pv = props[prop].verbosity
            if pv is None or verbosity < pv:
                # Setting the property's verbosity to None should hide the property
                continue

            flat_list = False
            if prop == "aliases":
                # Filter out any aliases hidden by the requested verbosity level
                with utils.verbosity_filter(self.resolver, verbosity):
                    value = self.aliases
            else:
                value = getattr(self, prop)
            if prop == "aliases" and not value:
                # Don't show the aliases row if none are set
                continue
            elif prop == "aliases" and verbosity < 3:
                value = value.keys()
                flat_list = True
            elif prop == "versions":
                value = self._dump_versions(value, verbosity=verbosity, color=color)

            ret.append(
                utils.dump_object(
                    value, label=f"{prop}:  ", flat_list=flat_list, color=color
                )
            )

        ret = "\n".join(ret)
        name = type(self).__name__
        if color:  # pragma: no cover
            # Only colorize the uri name not the entire title line
            title = (
                f"Dump of {name}({Fore.GREEN}'" f"{self.fullpath}'{Style.RESET_ALL})"
            )
        else:
            title = f"Dump of {name}('{self.fullpath}')"
        return utils.dump_title(title, ret, color=False)

    # Note: 'distros' needs to be processed before 'environment'
    @hab_property(verbosity=2, process_order=80)
    def environment(self):
        """A resolved set of environment variables that should be applied to
        configure an environment. Any values containing a empty string indicate
        that the variable should be unset.
        """
        if "environment" in self.frozen_data:
            return self.frozen_data["environment"].get(utils.Platform.name(), {})

        self.frozen_data["environment"] = {}

        # Merge the environment_config if defined
        if self.environment_config is not NotSet:
            self.merge_environment(self.environment_config)

        return self.frozen_data["environment"].get(utils.Platform.name(), {})

    @hab_property(verbosity=2)
    def environment_config(self):
        """A dictionary of operations to perform on environment variables.

        The top level dictionary defines the modification operation. Valid keys are
        "set", "unset", "prepend" and "append". Each of these keys contain the
        environment variable key/value pairs to be modified.

        Like Rez, the first set, prepend or append operation on a variable will replace
        the existing variable value. This quote from the Rez documentation explains why:
        "Why does this happen? Consider PYTHONPATH - if an initial overwrite did not
        happen, then any modules visible on PYTHONPATH before the rez environment was
        configured would still be there. This would mean you may not have a properly
        configured environment. If your system PyQt were on PYTHONPATH for example,
        and you used rez-env to set a different PyQt version, an attempt to import
        it within the configured environment would still, incorrectly, import the
        system version."

        Note however that this does not apply to the PATH env variable. You may
        only use append and prepend on that variable.
        """
        return self.frozen_data.get("environment_config", NotSet)

    @environment_config.setter
    def environment_config(self, env):
        self.frozen_data["environment_config"] = env
        self.frozen_data.pop("environment", None)

    @hab_property(verbosity=3)
    def filename(self):
        """The filename that defined this object. Any relative paths are
        relative to the directory of this file.
        """
        return self._filename

    @filename.setter
    def filename(self, filename):
        """A path like object. If a empty string is provided, ``Path(os.devnull)``
        will be used to prevent using an relative path.
        """
        # Cache the dirname so we only need to look it up once
        if not filename:
            self._filename = Path(os.devnull)
            self._dirname = Path(os.devnull)
        else:
            self._filename = Path(filename)
            self._dirname = self._filename.parent

    def format_environment_value(self, value, ext=None, platform=None):
        """Apply standard formatting to string values.

         If passed a list, tuple, dict, recursively calls this function on them
         converting any strings found. Any bool or int values are not modified.

        Args:
            value: The string to format.
            ext (str, optional): Language passed to ``hab.formatter.Formatter``
                for special formatters. In most cases this should not be used.
            platform (str, optional): Convert path values from the current
                platform to this path using `site.plaform_path`.

        Format Keys:
            relative_root: Add the dirname of self.filename or a empty string. Equivalent
                of using the `.` object for file paths. This removes the
                ambiguity of if a `.` should be treated as a relative file path
                or a literal relative_root. Houdini doesn't support the native slash
                direction on windows, so backslashes are replaced with forward slashes.
        """
        if isinstance(value, list):
            # Format the individual items if a list of args is used.
            return [
                self.format_environment_value(v, ext=ext, platform=platform)
                for v in value
            ]
        elif isinstance(value, tuple):
            # Format the individual items if a tuple of args is used.
            return tuple(
                self.format_environment_value(v, ext=ext, platform=platform)
                for v in value
            )
        elif isinstance(value, dict):
            # Format the values each dictionary pair
            return {
                k: self.format_environment_value(v, ext=ext, platform=platform)
                for k, v in value.items()
            }
        elif isinstance(value, (bool, int)):
            # Just return boolean values, no need to format
            return value

        # Include custom variables in the format dictionary.
        kwargs = {}
        if self.variables:
            kwargs.update(self.variables)

        # Custom variables do not override hab variables, ensure they are set
        # to the correct value.
        kwargs["relative_root"] = utils.path_forward_slash(self.dirname)
        ret = Formatter(ext).format(value, **kwargs)

        # Use site.the platform_path_maps to convert the result to the target platform
        if platform:
            ret = utils.path_forward_slash(
                self.resolver.site.platform_path_map(ret, platform)
            )

        return ret

    @property
    def fullpath(self):
        return self.separator.join([node.name for node in self.path])

    @classmethod
    def get_min_verbosity(cls, config, target, default=0):
        """Gets the desired min_verbosity setting for a given dictionary. If the
        desired target is not specified returns the global target, returning default
        if not defined.

        Args:
            config (dict): The config dict to get the desired verbosity level.
                Returns default if None is passed.
            target (str): The name of the desired verbosity level to return if defined.
            default (int, optional): Returned if unable to find a defined value.
        """
        if not config:
            return default
        # Get the min_verbosity dictionary
        verbosity = config.get("min_verbosity", {})
        if verbosity is NotSet:
            return default
        # If the requested target is defined, return its value
        if target in verbosity:
            return verbosity[target]
        # Otherwise return the default global value, defaulting to zero if
        # global was not defined
        return verbosity.get("global", default)

    @property
    def inherits(self):
        """Should this node inherit from a parent."""
        # Note: Sub-classes need to override this method to enable inheritance.
        return False

    def _load(self, filename, cached=True):
        """Sets self.filename and parses the json file returning the data dict.

        Args:
            filename (pathlib.Path): The file to load.
            cached (bool, optional): Enables loading of cached data instead of
                loading the data from disk.
        """
        self.filename = Path(filename)

        if cached:
            ret = self._cache().get(Path(filename).as_posix())
            if ret:
                logger.debug(f'Cached: "{filename}"')
                return ret

        logger.debug(f'Loading "{filename}"')
        return utils.load_json_file(self.filename)

    def load(self, filename, data=None):
        """Load this objects configuration from the given json filename.

        Args:
            filename (str): The json file to load the config from.
            data (dict, optional): If provided this dict is used instead of parsing
                the json file. In this case filename is ignored.
        """
        if data is None:
            data = self._load(filename)

        # Check for NotSet so sub-classes can set values before calling super
        if self.name is NotSet:
            self.name = data["name"]
        if self.variables is NotSet:
            self.variables = data.get("variables", NotSet)
        if "version" in data and self.version is NotSet:
            self.version = data.get("version")
        if self.distros is NotSet:
            self.distros = data.get("distros", NotSet)
        if self.environment_config is NotSet:
            self.environment_config = data.get("environment", NotSet)
        if self.min_verbosity is NotSet:
            self.min_verbosity = data.get("min_verbosity", NotSet)
        if self.optional_distros is NotSet:
            self.optional_distros = data.get("optional_distros", NotSet)

        if self.context is NotSet:
            # TODO: make these use override methods
            if self._context_method == "key":
                self.context = data.get("context", NotSet)
            elif self._context_method == "name":
                self.context = [data["name"]]

        return data

    def merge_environment(self, environment_config, obj=None):
        """Check and update environment with the provided environment config."""

        if obj is None:
            obj = self

        if environment_config is NotSet:
            # No environment_config dictionary was set, noting to do
            return

        merger = MergeDict(
            relative_root=self.dirname,
            platforms=self.resolver.site["platforms"],
            site=self.resolver.site,
        )
        merger.formatter = obj.format_environment_value
        merger.validator = self.check_environment
        # Flatten the site configuration down to per-platform configurations
        merger.apply_platform_wildcards(
            environment_config, output=self.frozen_data["environment"]
        )

    @hab_property(verbosity=2)
    def min_verbosity(self):
        return self.frozen_data.get("min_verbosity", NotSet)

    @min_verbosity.setter
    def min_verbosity(self, min_verbosity):
        self.frozen_data["min_verbosity"] = min_verbosity

    @hab_property(verbosity=1, group=0, process_order=40)
    def name(self):
        """The name of this object. See ``.context`` for how this is built into
        a full URI. `project_a/Sc001` would resolve into context: `["project_a"]`
        and name: `"Sc001"`.
        """
        return self.frozen_data.get("name", NotSet)

    @name.setter
    def name(self, name):
        self.frozen_data["name"] = name

    @hab_property(verbosity=1)
    def optional_distros(self):
        """Information about distros chosen to be optionally enabled for a config.

        The key is the distro including version specifier text. The value is a 2
        item list containing a description to shown next to the key and a bool
        indicating that it should be enabled by default when used.
        """
        return self.frozen_data.get("optional_distros", NotSet)

    @optional_distros.setter
    def optional_distros(self, value):
        self.frozen_data["optional_distros"] = value

    def reduced(self, resolver=None, uri=None):
        """Returns a new instance with the final settings applied respecting inheritance"""
        from . import FlatConfig

        return FlatConfig(self, resolver, uri=uri)

    @classmethod
    def shell_escape(cls, ext, value):
        """Apply any shell specific formatting like escape characters."""
        if ext == ".ps1":
            if isinstance(value, list):
                value = " ".join([v.replace(" ", "` ") for v in value])
            else:
                return value.replace(" ", "` ")
        if ext in (".sh", ""):
            # wrapping items in quotes takes care of escaping file paths
            if isinstance(value, list):
                value = subprocess.list2cmdline(value)
            else:
                return '"{}"'.format(value)
        if ext in (".bat", ".cmd"):
            if isinstance(value, list):
                value = subprocess.list2cmdline(value)
            else:
                return '"{}"'.format(value)
        return value

    @classmethod
    def shell_formats(cls, ext):
        """Returns a file ext specific dict that is used to write launch scripts"""
        ret = {}
        if ext in (".bat", ".cmd"):
            ret["launch"] = 'cmd.exe /k "{path}"\n'
        elif ext == ".ps1":
            ret["launch"] = (
                'powershell.exe{launch_args} -ExecutionPolicy Unrestricted -File "{path}"\n'
                "exit $LASTEXITCODE\n"
            )
        elif ext in (".sh", ""):  # Assume no ext is a .sh file
            # `set -e` propagates the error code returned by bash to the caller
            ret["launch"] = 'set -e\nbash --init-file "{path}"\n'

        return ret

    @property
    def uri(self):
        """The Uniform Resource Identifier for this object. This is a combination of
        its context and name properties separated by `/`"""
        if self._uri:
            return self._uri
        return self.fullpath

    def update_environ(self, env, alias_name=None, include_global=True, formatter=None):
        """Updates the given environment variable dictionary to conform with
        the hab environment specification.

        Args:
            env (dict): This dictionary is modified according to the hab
                definition. Often you will want to pass a copy of `os.environ`.
            alias_name (str, optional): If passed also apply any complex alias
                specific environment variable changes.
            include_global (bool, optional): Used to disable adding the global
                hab managed env vars. Disable this and use alias_name to only
                get the env vars set by the alias, not the global ones. This
                also adds `HAB_FREEZE` if possible.
            formatter (hab.formatter.Formatter, optional): Str formatter class
                used to format the env var values.
        """
        ext = utils.Platform.default_ext()
        if formatter is None:
            # Make sure to expand environment variables when formatting.
            formatter = Formatter(ext, expand=True)

        def _apply(data):
            for key, value in data.items():
                if value:
                    value = utils.Platform.collapse_paths(value, ext=ext, key=key)
                    value = formatter.format(value, key=key, value=value)
                    env[key] = value
                else:
                    env.pop(key, None)

        if include_global:
            _apply(self.environment)
            # Add the HAB_FREEZE environment variable documenting the entire
            # resolved hab configuration.
            if hasattr(self, "freeze") and "HAB_FREEZE" not in env:
                env["HAB_FREEZE"] = utils.encode_freeze(
                    self.freeze(), site=self.resolver.site
                )
        if alias_name:
            _apply(self.aliases[alias_name].get("environment", {}))

    @hab_property(verbosity=3)
    def variables(self):
        """A configurable dict of reusable key/value pairs to use when formatting
        text strings in the rest of the json file. This value is stored in the
        `variables` dictionary of the json file.
        """
        return self._variables

    @variables.setter
    def variables(self, variables):
        # Raise an exception if a reserved variable name is used.
        if variables and isinstance(variables, dict):
            invalid = ReservedVariableNameError._reserved_variable_names.intersection(
                variables
            )
            if invalid:
                raise ReservedVariableNameError(invalid, self.filename)
        self._variables = variables

    @property
    def version(self):
        """A `packaging.version.Version` representing the version of this object."""
        return self.frozen_data.get("version", NotSet)

    @version.setter
    def version(self, version):
        if version and not isinstance(version, Version):
            version = Version(version)
        self.frozen_data["version"] = version

    def generate_config_script(
        self,
        template,
        ext,
        alias_dir=None,
        args=None,
        create_launch=False,
        exit=False,
        launch=None,
    ):
        """Build a shell script for the requested template.

        Args:
            template (str): The name of the Jinja2 template file to generate with.
            ext (str): The file extension of the script to generate including leading `.`.

        Returns:
            str: The rendered script.
        """

        environment = Environment(
            loader=FileSystemLoader(str(TEMPLATES)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        template = environment.get_template(f"{template}{ext}")
        kwargs = dict(
            alias_dir=alias_dir,
            args=args,
            create_launch=create_launch,
            exit=exit,
            ext=ext,
            formatter=Formatter(ext),
            freeze=None,
            hab_cfg=self,
            launch_info={},
            utils=utils,
        )
        if hasattr(self, "freeze"):
            kwargs["freeze"] = utils.encode_freeze(
                self.freeze(), site=self.resolver.site
            )
        if launch:
            # Write additional args into the launch command. This may not properly
            # add quotes around windows file paths if writing a shell script.
            # At this point we have lost the original double quote the user used.
            if isinstance(args, list):
                if ext == ".ps1":
                    args = " {}".format(subprocess.list2cmdline(args))
                else:
                    args = " {}".format(self.shell_escape(ext, args))
            else:
                args = ""

            # Get the cmd to launch, raising useful errors if invalid
            if launch not in self.aliases:
                raise InvalidAliasError(launch, self)
            alias = self.aliases.get(launch, {})

            try:
                cmd = alias["cmd"]
            except KeyError:
                raise HabError(
                    f'Alias "{launch}" does not have "cmd" defined'
                ) from None

            cmd = self.shell_escape(ext, cmd)
            kwargs["launch_info"] = dict(key=launch, value=cmd, args=args)

        # Note: jinja2' seems to be inconsistent with its trailing newlines depending
        # on the template and its if statements, so force a single trailing newline
        return template.render(**kwargs).rstrip() + "\n"

    def generate_alias_script(self, template, ext, alias, cfg):
        """Build a shell script for aliases that require their own script files(batch).

        Args:
            template (str): The name of the Jinja2 template file to generate with.
            ext (str): The file extension of the script to generate including leading `.`.
            alias (str): The name of the alias to generate.
            cfg (dict): The configuration of the alias.

        Returns:
            str: The rendered script.
        """
        environment = Environment(
            loader=FileSystemLoader(str(TEMPLATES)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        template = environment.get_template(f"{template}{ext}")
        kwargs = dict(
            alias=alias,
            cfg=cfg,
            ext=ext,
            formatter=Formatter(ext),
            hab_cfg=self,
            utils=utils,
        )

        # Note: jinja2' seems to be inconsistent with its trailing newlines depending
        # on the template and its if statements, so force a single trailing newline
        return template.render(**kwargs).rstrip() + "\n"

    def _write_script(self, script_path, content):
        """Work function to save content to script script_path. If dump_scripts
        is enabled, script_path is ignored and content is printed instead.
        """
        if self.resolver.dump_scripts:
            self.print_script(script_path, content)
        else:
            with script_path.open("w") as fle:
                fle.write(content)

    def write_script(
        self, script_dir, ext, launch=None, exit=False, args=None, create_launch=False
    ):
        """Write the configuration to a script file to be run by terminal."""
        script_dir = Path(script_dir)
        config_script = script_dir / f"hab_config{ext}"
        alias_dir = script_dir / "aliases"
        shell = self.shell_formats(ext)

        content = self.generate_config_script(
            "config",
            ext,
            alias_dir=alias_dir,
            args=args,
            create_launch=create_launch,
            exit=exit,
            launch=launch,
        )
        self._write_script(config_script, content)

        # Handle aliases that can't be defined in memory(batch) by writing
        # additional scripts to disk
        if ext in (".bat", ".cmd") and hasattr(self, "aliases"):
            if not self.resolver.dump_scripts:
                alias_dir.mkdir(exist_ok=True)

            for alias, cfg in self.aliases.items():
                content = self.generate_alias_script("alias", ext, alias=alias, cfg=cfg)
                self._write_script(alias_dir / f"{alias}{ext}", content)

        if create_launch:
            launch_script = script_dir / f"hab_launch{ext}"
            launch_args = ""
            if ext == ".ps1":
                # If we want PowerShell to stay open after the script exits pass
                # `-NoExit` to the shell launch. Other shells allow us to simply
                # call exit at the end of the configure script.
                if not (exit and create_launch):
                    launch_args = " -NoExit"

            content = shell["launch"].format(
                path=config_script, launch_args=launch_args
            )
            self._write_script(launch_script, content)

    def print_script(self, filename, content):
        """Prints a header including the filename and content.

        Args:
            filename (pathlib.Path): The name of the file contents is to be
                written to.
            content (str): Shell script that is to be written to filename.
                If colorize is enabled, then syntax highlighting is applied
                based on filenames extension.
        """
        colorize = self.resolver.site.get("colorize", True)
        if colorize:
            from pygments import highlight
            from pygments.formatters import TerminalFormatter
            from pygments.lexers import get_lexer_for_filename

        # Print the name of the script being printed
        if colorize:
            header = f"{Fore.GREEN}-- Script: {filename} --{Fore.RESET}"
        else:
            header = f"-- Script: {filename} --"
        print(header)

        # Highlight and print the script contents
        if colorize:
            lexer = get_lexer_for_filename(filename)
            content = highlight(content, lexer, TerminalFormatter())

        print(content)
