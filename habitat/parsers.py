from __future__ import print_function
import anytree
import distutils.spawn
from .errors import DuplicateJsonError
from future.utils import with_metaclass
import json
import logging
import os
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version
from pprint import pformat
import sys
import six
import subprocess
import tabulate

logger = logging.getLogger(__name__)


class NotSet(object):
    """The data for this property is not currently set."""

    def __bool__(self):
        """NotSet should be treated as False when booled Python 3"""
        return False

    def __nonzero__(self):
        """NotSet should be treated as False when booled Python 2"""
        return False

    def __str__(self):
        return "NotSet"


# Make this a singleton so it works like a boolean False for if statements.
NotSet = NotSet()


class HabitatProperty(property):
    """The @property decorator that can be type checked by the `HabitatMeta` metaclass

    Any properties using this decorator will have their name added to `_properties`.
    """


class HabitatMeta(type):
    """Scans for HabitatProperties and adds their name to the `_properties` set."""

    def __new__(cls, name, bases, dct):
        desc = set()
        for base in bases:
            if hasattr(base, "_properties"):
                desc.update(base._properties)

        for k, v in dct.items():
            if isinstance(v, HabitatProperty):
                desc.add(k)
        dct["_properties"] = desc
        return type.__new__(cls, name, bases, dct)


class HabitatBase(with_metaclass(HabitatMeta, anytree.NodeMixin)):
    """Base class for the various parser classes. Provides most of the functionality
    to parse a json configuration file and resolve it for use in habitat.

    Args:
        forest (dict): A dictionary map used to calculate the context when resolving
            this object.
        resolver (habitat.Resolver): The Resolver used to lookup requirements.
        filename (str, optional): Automatically call load on this filename.
        parent (habitat.parsers.HabitatBase, optional): Parent for this object.
        root_paths (set, optional): The base glob path being processed to create the
            HabitatBase objects for this forest. If two
    """

    # Subclasses can change this to control how data is tweaked by the load method.
    _context_method = "key"
    # A instance of this class is used to build a parent anytree item if no
    # configuration was processed yet to fill in that node. This is set to the
    # Placeholder class after it is defined below. This allows the
    # ApplicationVersion class to use Application as its placeholder
    _placeholder = None
    # Configure anytree to use `:` instead of `/` as the separator
    separator = ":"

    def __init__(self, forest, resolver, filename=None, parent=None, root_paths=None):
        super(HabitatBase, self).__init__()
        self._environment = None
        self._filename = None
        self._dirname = None
        self._platform_override = None
        self._requires = None
        self._uri = NotSet
        self.parent = parent
        self.root_paths = set()
        if root_paths:
            self.root_paths = root_paths
        self.forest = forest
        self.resolver = resolver
        self._init_variables()
        if filename:
            self.load(filename)

    def __repr__(self):
        cls = type(self)
        return "{}.{}('{}')".format(cls.__module__, cls.__name__, self.fullpath)

    def _init_variables(self):
        """Called by __init__. Subclasses can override this to set default variable
        values before self.load is called if a filename is passed.
        """
        # The context setter has a lot of overhead don't use it to set the default
        self._context = NotSet
        self.distros = NotSet
        self.environment_config = NotSet
        self.name = NotSet
        # self.requires = NotSet
        self.version = NotSet

    @property
    def _platform(self):
        """Returns the current operating system `windows` or `linux`."""
        if self._platform_override:
            # Provide a method for testing to always test for running on a specific os
            return self._platform_override
        return "windows" if sys.platform == "win32" else "linux"

    def check_environment(self, environment_config):
        """Check that the environment config only makes valid adjustments.
        For example, check that we never replace path, only append/prepend are allowed.
        """
        for operation in ("unset", "set"):
            if operation not in environment_config:
                continue

            keys = environment_config.get(operation, [])
            if operation == "set":
                # set is a dictionary while unset is a list
                keys = keys.keys()

            for key in keys:
                if key.lower() == "path":
                    if operation == "set":
                        key = environment_config[operation][key]
                        msg = 'You can not use PATH for the set operation: "{}"'
                    else:
                        msg = "You can not unset PATH"
                    raise ValueError(msg.format(key))

    @property
    def context(self):
        """A list of parent context strings."""
        return self._context

    @context.setter
    def context(self, context):
        self._context = context

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
        `self.format_environment_value` to fill the "dot" variable.
        """
        return self._dirname

    @HabitatProperty
    def distros(self):
        return self._distros

    @distros.setter
    def distros(self, distros):
        # Ensure the contents are converted to Requirement objects
        if distros:
            # Applications can define distros as lists, convert to a dict
            if isinstance(distros, list):
                distros = {k: None for k in distros}

            for d in distros.keys():
                if not isinstance(d, Requirement):
                    # Replace the existing requirement string with a requirement object
                    distros[Requirement(d)] = distros[d]
                    del distros[d]
        self._distros = distros

    def dump(self, environment=True, environment_config=False):
        """Return a string of the properties and their values.

        Args:
            environment (bool, optional): Show the environment value.
            environment_config (bool, optional): Show the environment_config value.

        Returns:
            str: The configuration converted to a string
        """
        ret = []
        # Update what properties are shown in the dump
        props = set(self._properties)
        for k, v in (
            ("environment", environment),
            ("environment_config", environment_config),
        ):
            if v:
                props.add(k)
            else:
                props.discard(k)

        for prop in sorted(props):
            value = getattr(self, prop)
            # Custom formatting of values for readability
            if value is NotSet:
                value = "<NotSet>"
            if prop == "versions":
                value = sorted([v.name for v in value])
            if prop == "environment" and value:
                # Format path environment variables so they are easy to read
                # and take up more vertical space than horizontal space
                rows = []
                for key in sorted(value):
                    val = "{}: ".format(key)
                    row = []
                    for v in value[key].split(os.pathsep):
                        row.append("{}{}".format(val, v))
                        val = " " * len(val)
                    rows.append("{}\n".format(os.pathsep).join(row))
                value = "\n".join(rows)

            if isinstance(value, (list, dict)):
                # Format long data types into multiple rows for readability
                lines = pformat(value)
                for line in lines.split("\n"):
                    ret.append((prop, line))
                    # Clear the prop name so we only add it once on the left
                    prop = ""
            else:
                ret.append((prop, value))

        ret = tabulate.tabulate(ret)

        # Build a header for the details table
        cls = type(self)
        return "Dump of {}('{}')\n{}".format(cls.__name__, self.fullpath, ret)

    @property
    def environment(self):
        """A resolved set of environment variables that should be applied to
        configure an environment. Any values containing a empty string indicate
        that the variable should be unset.
        """
        if self.environment_config is NotSet and self._environment is None:
            self._environment = {}

        if self._environment is None:
            self._environment = {}
            self.update_environment(self.environment_config)

        return self._environment

    @HabitatProperty
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
        return self._environment_config

    @environment_config.setter
    def environment_config(self, env):
        self._environment_config = env
        self._environment = None

    @property
    def filename(self):
        """The filename that defined this object. Any relative paths are
        relative to the directory of this file.
        """
        return self._filename

    @filename.setter
    def filename(self, filename):
        self._filename = filename
        # Cache the dirname so we only need to look it up once
        if filename:
            self._dirname = os.path.dirname(filename)
        else:
            self._dirname = ""

    def format_environment_value(self, value):
        """Apply standard formatting to environment variable values.

        Args:
            value (str): The string to format

        Format Keys:
            dot: Add the dirname of self.filename or a empty string. Equivalent
                of using the `.` object for file paths. This removes the
                ambiguity of if a `.` should be treated as a relative file path
                or a literal dot. Houdini doesn't support the native slash direction
                on windows, so backslashes are replaced with forward slashes.
        """
        return value.format(dot=self.dirname.replace("\\", "/"))

    @property
    def fullpath(self):
        return self.separator.join([""] + [node.name for node in self.path])

    def _load(self, filename):
        """Sets self.filename and parses the json file returning the data."""
        self.filename = filename
        with open(filename, "r") as fle:
            try:
                data = json.load(fle)
            except ValueError as e:
                # Include the filename in the traceback to make debugging easier
                msg = '{} Filename: "{}"'.format(e, filename)
                # Workaround some inconsistencies between python 2 and 3 json implementations.
                # Python 3 uses JsonDecodeError that requires two extra arguments.
                try:
                    args = (msg, e.doc, e.pos)
                except AttributeError:
                    args = (msg,)

                six.reraise(
                    type(e),
                    type(e)(*args),
                    sys.exc_info()[2],
                )
        return data

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

    @HabitatProperty
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    def reduced(self, resolver=None, uri=None):
        """Returns a new instance with the final settings applied respecting inheritance"""
        return FlatConfig(self, resolver, uri=uri)

    @HabitatProperty
    def requires(self):
        if self.distros is NotSet:
            return []

        if self._requires is None:
            requires = self.resolver.resolve_requirements(self.distros)
            self._requires = sorted([str(r) for r in requires.values()])

        return self._requires

    @classmethod
    def shell_escape(cls, ext, value):
        """Apply any shell specific formatting like escape characters."""
        if ext == ".ps1":
            return value.replace(" ", "` ")
        if ext in (".sh", ""):
            return value.replace(" ", "\\ ")
        return value

    @classmethod
    def cygpath(cls, paths):
        """Convert file paths from windows to cygwin/mingw file paths.
        If on win32 and can find the cygpath exe, calls it with subprocess to convert
        the provided paths to work in cygwin.

        Args:
            paths (list): A list of windows file paths to convert to unix paths.

        Returns:
            list: The possibly converted file paths.
        """
        if paths:
            if sys.platform == "win32" and distutils.spawn.find_executable("cygpath"):
                cmd = ["cygpath", "-ua"]
                cmd.extend(paths)
                paths = subprocess.check_output(cmd).decode()
                return paths.split("\n")
        return paths

    @classmethod
    def shell_formats(cls, ext):
        """Returns a file ext specific dict that is used to write launch scripts"""
        ret = {
            "postfix": "",
            "prefix": "",
        }
        if ext in (".bat", ".cmd"):
            ret["alias_setter"] = 'doskey {key}="{value}" $*\n'
            ret["comment"] = "REM "
            ret["env_setter"] = 'set "{key}={value}"\n'
            ret["env_unsetter"] = 'set "{key}="\n'
            ret["postfix"] = "@ECHO ON\n"
            ret["prefix"] = "@ECHO OFF\n"
            ret["prompt"] = 'set "PROMPT=[{uri}] $P$G"\n'
            ret["launch"] = 'cmd.exe /k "{path}"\n'
        elif ext == ".ps1":
            ret["alias_setter"] = "function {key}() {{ {value} $args }}\n"
            ret["comment"] = "# "
            ret["env_setter"] = '$env:{key} = "{value}"\n'
            ret[
                "env_unsetter"
            ] = "Remove-Item Env:\\{key} -ErrorAction SilentlyContinue\n"
            ret["prompt"] = "function PROMPT {{'[{uri}] ' + $(Get-Location) + '>'}}\n"
            ret[
                "launch"
            ] = 'powershell.exe -NoExit -ExecutionPolicy Unrestricted . "{path}"\n'
        elif ext in (".sh", ""):  # Assume no ext is a .sh file
            ret[
                "alias_setter"
            ] = 'function {key}() {{ {value} "$@"; }};export -f {key};\n'
            ret["comment"] = "# "
            ret["env_setter"] = 'export {key}="{value}"\n'
            ret["env_unsetter"] = "unset {key}\n"
            # For now just tack the habitat uri onto the prompt
            ret["prompt"] = 'export PS1="[{uri}] $PS1"\n'
            ret["launch"] = "bash --init-file {path}\n"

        return ret

    def update_environment(self, environment_config, obj=None):
        """Check and update environment with the provided environment config."""
        if obj is None:
            obj = self

        # If os_specific is specified, we are defining environment variables per-os
        # not globally. Lookup the current os's configuration.
        if environment_config.get("os_specific", False):
            environment_config = environment_config.get(self._platform, {})

        self.check_environment(environment_config)

        if "unset" in environment_config:
            # When applying the env vars later None will trigger removing the env var.
            # The other operations may end up replacing this value.
            self._environment.update({key: "" for key in environment_config["unset"]})
        # set, prepend, append are all treated as set operations, this lets us override
        # existing user and system variable values without them causing issues.
        if "set" in environment_config:
            for key, value in environment_config["set"].items():
                self._environment[key] = obj.format_environment_value(value)
        for operation in ("prepend", "append"):
            if operation not in environment_config:
                continue
            for key, value in environment_config[operation].items():
                existing = self._environment.get(key, "")
                if existing:
                    if operation == "prepend":
                        value = [value, existing]
                    else:
                        value = [existing, value]
                else:
                    value = [value]
                self._environment[key] = obj.format_environment_value(
                    os.pathsep.join(value)
                )

    @property
    def uri(self):
        if self._uri:
            return self._uri
        return self.fullpath

    @property
    def version(self):
        """A `packaging.version.Version` representing the version of this object."""
        return self._version

    @version.setter
    def version(self, version):
        if version and not isinstance(version, Version):
            version = Version(version)
        self._version = version

    def write_script(self, config_script, launch_script=None):
        """Write the configuration to a script file to be run by terminal."""
        _, ext = os.path.splitext(config_script)
        shell = self.shell_formats(ext)

        with open(config_script, "w") as fle:
            if shell["prefix"]:
                fle.write(shell["prefix"])
            # Create a custom prompt
            fle.write("{}Customizing the prompt\n".format(shell["comment"]))
            fle.write(shell["prompt"].format(uri=self.uri))
            fle.write("\n")

            if self.environment:
                fle.write("{}Setting environment variables:\n".format(shell["comment"]))
                for key, value in self.environment.items():
                    setter = shell["env_setter"]
                    if not value:
                        setter = shell["env_unsetter"]
                    fle.write(setter.format(key=key, value=value))

            if hasattr(self, "aliases") and self.aliases:
                if self.environment:
                    # Only add a blank line if we wrote environment modifications
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
            if shell["postfix"]:
                fle.write(shell["postfix"])

        if launch_script:
            with open(launch_script, "w") as fle:
                paths = self.cygpath([config_script])
                fle.write(shell["launch"].format(path=paths[0]))


class Application(HabitatBase):
    def latest_version(self, specifier):
        """Returns the newest version available matching the specifier"""
        versions = self.matching_versions(specifier)
        try:
            version = max(versions)
        except ValueError:
            raise Exception('Unable to find a valid version for "{}"'.format(specifier))
        return self.versions[version]

    def matching_versions(self, specification):
        """Returns a list of versions available matching the version specification.
        See `packaging.requirements` for details on valid requirements, but it
        should be the same as pip requirements.
        """
        if isinstance(specification, Requirement):
            specifier = specification.specifier
        elif isinstance(specification, SpecifierSet):
            specifier = specification
        else:
            specifier = Requirement(specification).specifier
        return specifier.filter(self.versions.keys())

    @property
    def versions(self):
        """A dict of available application versions"""
        return {c.version: c for c in self.children}


class ApplicationVersion(HabitatBase):
    _context_method = "name"
    _placeholder = Application

    def _init_variables(self):
        super(ApplicationVersion, self)._init_variables()
        self.aliases = NotSet

    @HabitatProperty
    def aliases(self):
        return self._aliases

    @aliases.setter
    def aliases(self, aliases):
        self._aliases = aliases

    def load(self, filename):
        # Fill in the ApplicationVersion specific settings before calling super
        data = self._load(filename)
        self.aliases = data.get("aliases", NotSet)

        if "version" in data:
            self.version = data["version"]
        else:
            # If version is not defined in json data extract it from the parent
            # directory name. This allows for simpler distribution without needing
            # to modify version controlled files.
            self.version = os.path.basename(os.path.dirname(filename))

        # The name should be the version == specifier.
        self.application_name = data.get("name")
        self.name = u"{}=={}".format(self.application_name, self.version)

        data = super(ApplicationVersion, self).load(filename, data=data)

        return data

    @HabitatProperty
    def version(self):
        return super(ApplicationVersion, self).version

    @version.setter
    def version(self, version):
        # NOTE: super doesn't work for a @property.setter
        if version and not isinstance(version, Version):
            version = Version(version)
        self._version = version


class Config(HabitatBase):
    def _init_variables(self):
        super(Config, self)._init_variables()
        self.inherits = NotSet

    @HabitatProperty
    def inherits(self):
        return self._inherits

    @inherits.setter
    def inherits(self, inherits):
        self._inherits = inherits

    def load(self, filename):
        data = super(Config, self).load(filename)
        self.inherits = data.get("inherits", NotSet)
        return data

    @HabitatProperty
    def uri(self):
        # Mark uri as a HabitatProperty so it is included in _properties
        return super(Config, self).uri


class FlatConfig(Config):
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
        for attrname in self._properties:
            if attrname == "uri":
                # TODO: Add detection of setters to HabitatProperty and don't set values without setters
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

    @HabitatProperty
    def aliases(self):
        ret = {}
        for version in self.versions:
            if version.aliases:
                # cygpath currently requires a subprocess call, but we can pass multiple
                # paths to it to process all of them at once. If using windows and
                # cygpath is found, use it to translate the paths so they work
                aliases_def = version.aliases.get(self._platform, [])
                aliases = self.cygpath([a[1] for a in aliases_def])

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
        return self.separator.join([""] + [name for name in self.context] + [self.name])

    @HabitatProperty
    def versions(self):
        if self._distros is NotSet:
            return []

        if self._versions is None:
            self._versions = []
            reqs = self.resolver.resolve_requirements(self.distros)
            for req in reqs.values():
                self._versions.append(self.resolver.find_distro(req))

        return self._versions


class Placeholder(HabitatBase):
    """Provides an parent node for a child if one hasn't been created yet.
    This node will be replaced in the tree if a node is loaded for this position.
    """


# This is the first place where both HabitatBase and its subclass Placeholder
# are defined, so this is where we have to set _placeholder.
HabitatBase._placeholder = Placeholder
