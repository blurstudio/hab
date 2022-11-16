from __future__ import print_function

import logging
import os
import subprocess
from pathlib import Path

import anytree
import colorama
from packaging.version import Version

from .. import NotSet, utils
from ..errors import DuplicateJsonError
from ..formatter import Formatter
from ..site import MergeDict
from ..solvers import Solver
from .meta import HabMeta, hab_property

logger = logging.getLogger(__name__)


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
        super(HabBase, self).__init__()
        self.frozen_data = {}
        self._filename = None
        self._dirname = None
        self._distros = NotSet
        self._platform_override = None
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

    @classmethod
    def _dump_versions(cls, value, verbosity=0, color=None):
        """Returns the version information for this object as a list of strings."""
        if verbosity < 3:
            # Only show the names of the versions
            return sorted([v.name for v in value], key=lambda i: i.lower())

        # Include the definition of the version's path for debugging
        if color:  # pragma: no cover
            fmt = f"{colorama.Fore.GREEN}{{}}{colorama.Style.RESET_ALL}:  {{}}"
        else:
            fmt = "{}:  {}"
        return [
            fmt.format(v.name, v.filename)
            for v in sorted(value, key=lambda i: i.name.lower())
        ]

    @property
    def _platform(self):
        """Returns the current operating system `windows` or `linux`."""
        if self._platform_override:
            # Provide a method for testing to always test for running on a specific os
            return self._platform_override
        return utils.platform()

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
            color = self.resolver.site.get('colorize', True)

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
            if verbosity < props[prop].verbosity:
                continue

            value = getattr(self, prop)
            flat_list = False
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
                    value, label=f'{prop}:  ', flat_list=flat_list, color=color
                )
            )

        ret = '\n'.join(ret)
        name = type(self).__name__
        if color:  # pragma: no cover
            # Only colorize the uri name not the entire title line
            title = (
                f"Dump of {name}({colorama.Fore.GREEN}'"
                f"{self.fullpath}'{colorama.Style.RESET_ALL})"
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
            return self.frozen_data["environment"].get(self._platform, {})

        self.frozen_data["environment"] = {}

        # Merge the environment_config if defined
        if self.environment_config is not NotSet:
            self.merge_environment(self.environment_config)

        return self.frozen_data["environment"].get(self._platform, {})

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

    @property
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
        """Apply standard formatting to environment variable values.

        Args:
            value (str): The string to format
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

        # Expand and format any variables like "relative_root" using the current
        # platform for paths.
        kwargs = dict(relative_root=utils.path_forward_slash(self.dirname))
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

    def _load(self, filename):
        """Sets self.filename and parses the json file returning the data."""
        self.filename = Path(filename)
        logger.debug('Loading "{}"'.format(filename))
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
        if "version" in data and self.version is NotSet:
            self.version = data.get("version")
        if self.distros is NotSet:
            self.distros = data.get("distros", NotSet)
        if self.environment_config is NotSet:
            self.environment_config = data.get("environment", NotSet)

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
            platforms=self.resolver.site['platforms'],
            site=self.resolver.site,
        )
        merger.formatter = obj.format_environment_value
        merger.validator = self.check_environment
        # Flatten the site configuration down to per-platform configurations
        merger.apply_platform_wildcards(
            environment_config, output=self.frozen_data["environment"]
        )

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

    def reduced(self, resolver=None, uri=None):
        """Returns a new instance with the final settings applied respecting inheritance"""
        from . import FlatConfig

        return FlatConfig(self, resolver, uri=uri)

    @classmethod
    def shell_escape(cls, ext, value):
        """Apply any shell specific formatting like escape characters."""
        if ext == ".ps1":
            if isinstance(value, list):
                value = ' '.join([v.replace(" ", "` ") for v in value])
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
        ret = {
            "postfix": "",
            "prefix": "",
        }
        if ext in (".bat", ".cmd"):
            ret["alias_setter"] = 'C:\\Windows\\System32\\doskey.exe {key}={value} $*\n'
            ret["comment"] = "REM "
            ret["env_setter"] = 'set "{key}={value}"\n'
            ret["env_unsetter"] = 'set "{key}="\n'
            ret["postfix"] = "@ECHO ON\n"
            ret["prefix"] = "@ECHO OFF\n"
            ret["prompt"] = 'set "PROMPT=[{uri}] $P$G"\n'
            ret["launch"] = 'cmd.exe /k "{path}"\n'
            # You can't directly call a doskey alias in a batch script
            ret["run_alias"] = '{value}{args}\n'
        elif ext == ".ps1":
            ret["alias_setter"] = "function {key}() {{ {value} $args }}\n"
            ret["comment"] = "# "
            ret["env_setter"] = '$env:{key} = "{value}"\n'
            ret[
                "env_unsetter"
            ] = "Remove-Item Env:\\{key} -ErrorAction SilentlyContinue\n"
            # PROMPT is evaluated every time it is displayed so use the env var
            ret["prompt"] = 'function PROMPT {{"[$env:HAB_URI] $(Get-Location)>"}}\n'
            ret[
                "launch"
            ] = 'powershell.exe -NoExit -ExecutionPolicy Unrestricted . "{path}"\n'
            # Simply call the alias
            ret["run_alias"] = "{key}{args}\n"
        elif ext in (".sh", ""):  # Assume no ext is a .sh file
            ret[
                "alias_setter"
            ] = 'function {key}() {{ {value} "$@"; }};export -f {key};\n'
            ret["comment"] = "# "
            ret["env_setter"] = 'export {key}="{value}"\n'
            ret["env_unsetter"] = "unset {key}\n"
            # For now just tack the hab uri onto the prompt
            ret["prompt"] = 'export PS1="[{uri}] $PS1"\n'
            ret["launch"] = 'bash --init-file "{path}"\n'
            # Simply call the alias
            ret["run_alias"] = "{key}{args}\n"

        return ret

    @property
    def uri(self):
        """The Uniform Resource Identifier for this object. This is a combination of
        its context and name properties separated by `/`"""
        if self._uri:
            return self._uri
        return self.fullpath

    @property
    def version(self):
        """A `packaging.version.Version` representing the version of this object."""
        return self.frozen_data.get("version", NotSet)

    @version.setter
    def version(self, version):
        if version and not isinstance(version, Version):
            version = Version(version)
        self.frozen_data["version"] = version

    def write_script(
        self, script_dir, ext, launch=None, exit=False, args=None, create_launch=False
    ):
        """Write the configuration to a script file to be run by terminal."""
        script_dir = Path(script_dir)
        config_script = script_dir / f'hab_config{ext}'
        shell = self.shell_formats(ext)

        with config_script.open("w") as fle:
            if shell["prefix"]:
                fle.write(shell["prefix"])

            # Create a custom prompt
            fle.write("{}Customize the prompt\n".format(shell["comment"]))
            fle.write(shell["prompt"].format(uri=self.uri))
            fle.write("\n")

            fle.write("{}Setting environment variables:\n".format(shell["comment"]))
            for key, value in self.environment.items():
                setter = shell["env_setter"]
                if value:
                    value = utils.collapse_paths(value)
                    # Process any env conversion keys into the shell specific values.
                    # For example convert `{PATH!e}` to `$PATH` if this is an.sh file
                    value = Formatter(ext).format(value, key=key, value=value)
                else:
                    setter = shell["env_unsetter"]
                fle.write(setter.format(key=key, value=value))

            if hasattr(self, "freeze"):
                # Always write the HAB_FREEZE environment variable
                value = utils.encode_freeze(self.freeze())
                fle.write(setter.format(key="HAB_FREEZE", value=value))

            if hasattr(self, "aliases") and self.aliases:
                fle.write("\n")

                fle.write(
                    "{}Creating aliases to launch programs:\n".format(shell["comment"])
                )
                for alias in self.aliases:
                    fle.write(
                        shell["alias_setter"].format(
                            key=alias, value=self.shell_escape(ext, self.aliases[alias])
                        )
                    )

            # If launch was passed, call the requested command at the end of the script
            if launch:
                # Write additional args into the launch command. This may not properly
                # add quotes around windows file paths if writing a shell script.
                # At this point we have lost the original double quote the user used.
                if isinstance(args, list):
                    args = ' {}'.format(self.shell_escape(ext, args))
                else:
                    args = ''

                launch_info = dict(
                    key=launch,
                    value=self.shell_escape(ext, self.aliases.get(launch, "")),
                    args=args,
                )
                fle.write("\n")
                fle.write("{}Run the requested command\n".format(shell["comment"]))
                fle.write(shell["run_alias"].format(**launch_info))

            # When using `hab launch`, we need to exit the shell that launch_script is
            # going to create when the alias exits.
            if exit and create_launch:
                fle.write("\n")
                fle.write("{}\n".format(shell.get("exit", "exit")))

            if shell["postfix"]:
                fle.write(shell["postfix"])

        if create_launch:
            launch_script = script_dir / f'hab_launch{ext}'
            with launch_script.open("w") as fle:
                fle.write(shell["launch"].format(path=config_script))
