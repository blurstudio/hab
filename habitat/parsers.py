from __future__ import print_function
import anytree
from future.utils import with_metaclass
import json
import logging
import os
from packaging.version import Version
from pprint import pformat
import re
import sys
import six
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
    """The @property decorator that can be type checked by the metaclass"""


class HabitatMeta(type):
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
    separator = ":"

    def __init__(self, forest, filename=None, parent=None):
        super(HabitatBase, self).__init__()
        self._environment = None
        self._filename = None
        self._dirname = None
        self.parent = parent
        self.forest = forest
        self._init_variables()
        if filename:
            self.load(filename)

    def __repr__(self):
        cls = type(self)
        return "{}.{}({})".format(cls.__module__, cls.__name__, self.fullpath)

    def _init_variables(self):
        """Called by __init__. Subclasses can override this to set default variable
        values before self.load is called if a filename is passed.
        """
        # The context setter has a lot of overhead don't use it to set the default
        self._context = NotSet
        self.environment_config = NotSet
        self.name = NotSet
        self.requires = NotSet
        self.version = NotSet

    @property
    def context(self):
        return self._context

    @context.setter
    def context(self, context):
        self._context = context

        if not self.context:
            # Add the root of this tree to the forest
            if self.name in self.forest:
                # Preserve the children of the placeholder object if it exists
                if not isinstance(self.forest[self.name], Placeholder):
                    raise ValueError("Tree root {} is already set".format(self.name))
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
                root = Placeholder(self.forest)
                root.name = root_name
                self.forest[root_name] = root
                logger.debug("Created placeholder root: {}".format(root.fullpath))

            # Process the intermediate parents
            for child_name in self.context[1:]:
                try:
                    root = resolver.get(root, child_name)
                    logger.debug("Found intermediary: {}".format(root.fullpath))
                except anytree.resolver.ResolverError:
                    root = Placeholder(self.forest, parent=root)
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
                if isinstance(target, Placeholder):
                    # replace the placeholder with self
                    self.parent = target.parent
                    self.children = target.children
                    # Remove the placeholder from the tree
                    target.parent = None
                    logger.debug("Removing placeholder: {}".format(target.fullpath))
                else:
                    # TODO: Better exception or handle this differently
                    raise ValueError(
                        'Can not add "{}", the context is already set'.format(
                            self.fullpath
                        )
                    )

    @property
    def dirname(self):
        """The directory name of `self.filename`. This value is used to by
        `self.format_environment_value` to fill the "dot" variable.
        """
        return self._dirname

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
            if value is NotSet:
                value = "<NotSet>"
            if isinstance(value, (list, dict)):
                # Format long data types into multiple rows for readability
                lines = pformat(value)
                for line in lines.split("\n"):
                    ret.append((prop, line))
                    # Clear the prop name so we only add it once on the left
                    prop = ""
            else:
                ret.append((prop, value))
        return tabulate.tabulate(ret)

    @property
    def environment(self):
        """A resolved set of environment variables that should be applied to
        configure an environment. Any values containing a empty string indicate
        that the variable should be unset.
        """
        if self.environment_config is NotSet:
            return {}

        if self._environment is None:
            # Check that we never replace path, it should only appended/prepended
            for operation in ("unset", "set"):
                keys = self.environment_config.get(operation, [])
                if operation == "set":
                    # set is a dictionary while unset is a list
                    keys = keys.keys()

                for key in keys:
                    if key.lower() == "path":
                        if operation == "set":
                            key = self.environment_config[operation][key]
                            msg = 'You can not use PATH for the set operation: "{}"'
                        else:
                            msg = "You can not unset PATH"
                        raise ValueError(msg.format(key))

            self._environment = {}
            if "unset" in self.environment_config:
                # When applying the env vars later None will trigger removing the env var.
                # The other operations may end up replacing this value.
                self._environment.update(
                    {key: "" for key in self.environment_config["unset"]}
                )
            # set, prepend, append are all treated as set operations, this lets us override
            # existing user and system variable values without them causing issues.
            if "set" in self.environment_config:
                for key, value in self.environment_config["set"].items():
                    self._environment[key] = self.format_environment_value(value)
            for operation in ("prepend", "append"):
                if operation not in self.environment_config:
                    continue
                for key, value in self.environment_config[operation].items():
                    existing = self._environment.get(key, "")
                    if existing:
                        if operation == "prepend":
                            value = [value, existing]
                        else:
                            value = [existing, value]
                    else:
                        value = [value]
                    self._environment[key] = self.format_environment_value(
                        os.pathsep.join(value)
                    )

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
                or a literal dot.
        """
        return value.format(dot=self.dirname)

    @property
    def fullpath(self):
        return self.separator.join([""] + [node.name for node in self.path])

    def load(self, filename):
        self.filename = filename
        with open(filename, "r") as fle:
            try:
                data = json.load(fle)
            except ValueError as e:
                # Include the filename in the traceback to make debugging easier
                six.reraise(
                    type(e),
                    type(e)('{} Filename: "{}"'.format(e, filename)),
                    sys.exc_info()[2],
                )
        self.name = data["name"]
        self.requires = data.get("requires", NotSet)
        if "version" in data:
            self.version = Version(data.get("version"))
        self.environment_config = data.get("environment", NotSet)
        self.context = data.get("context", NotSet)

        return data

    @HabitatProperty
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    def reduced(self, resolver=None):
        """Returns a new instance with the final settings applied respecting inheritance"""
        ret = type(self)(self.forest)
        ret._context = self.context
        for attrname in ret._properties:
            setattr(ret, attrname, getattr(self, attrname))
        return ret

    @HabitatProperty
    def requires(self):
        return self._requires

    @requires.setter
    def requires(self, requires):
        self._requires = requires

    @property
    def version(self):
        return self._version

    @version.setter
    def version(self, version):
        self._version = version

    def write_script(self, filename):
        """Write the configuration to a script file to be run by terminal."""
        _, ext = os.path.splitext(filename)
        if ext in (".bat", ".cmd"):
            comment = "REM "
            env_setter = 'set "{key}={value}"\n'
            env_unsetter = 'set "{key}="\n'
            alias_setter = 'doskey {key}="{value}" $*\n'
        elif ext == ".ps1":
            comment = "# "
            env_setter = '$env:{key} = "{value}"\n'
            env_unsetter = "Remove-Item Env: {key}\n"
            alias_setter = "function {key}() {{ {value} $args }}\n"
        elif ext == ".sh":
            comment = "# "
            env_setter = 'export {key}="{value}"\n'
            env_unsetter = "unset {key}\n"
            alias_setter = 'function {key}() {{ {value} "$@"; }};export -f {key};\n'

        # TODO: Resolve aliases from distro config
        # aliases = []
        aliases = {
            "windows": [
                ["maya", "C:\\Program Files\\Autodesk\\Maya2020\\bin\\maya.exe"],
                ["mayapy", "C:\\Program Files\\Autodesk\\Maya2020\\bin\\mayapy.exe"],
                ["stext", "C:\\Program Files\\Sublime Text 3\\sublime_text.exe"],
            ],
            "linux": [
                ["maya", r"/C/Program\ Files/Autodesk/Maya2020/bin/maya.exe"],
                ["mayapy", r"/C/Program\ Files/Autodesk/Maya2020/bin/mayapy.exe"],
            ],
            "*": [["example", "{relative}/all_platform_example"]],
        }["windows"]

        with open(filename, "w") as fle:
            if self.environment:
                fle.write("{}Setting environment variables:\n".format(comment))
                for key, value in self.environment.items():
                    setter = env_setter
                    if not value:
                        setter = env_unsetter
                    fle.write(setter.format(key=key, value=value))
            if aliases:
                if self.environment:
                    # Only add a blank line if we wrote environment modifications
                    fle.write("\n")
                fle.write("{}Creating aliases to launch programs:\n".format(comment))
                for alias in aliases:
                    fle.write(alias_setter.format(key=alias[0], value=alias[1]))
        print(open(filename).read())

    # TODO: this is probably not needed, remove it
    @classmethod
    def current_script_type(cls):
        """Checks the current process to figure out what type of terminal
        python is running in.

        Returns:
            str: "powershell", "cmd", "bash" or None.
        """
        if sys.platform == "win32":
            print("windows")
            # Check if we are running a command prompt or power shell
            import psutil

            proc = psutil.Process(os.getpid())
            while proc:
                proc = proc.parent()
                if proc:
                    name = proc.name()
                    print(name)
                    # See if it is Windows PowerShell (powershell.exe) or
                    # PowerShell Core (pwsh[.exe]):
                    if bool(re.match("pwsh|pwsh.exe|powershell.exe", name)):
                        return "powershell"
                    elif name == "cmd.exe":
                        return "cmd"
                    elif name == "bash.exe":
                        return "bash"
        else:
            # TODO: support other script types?
            return "bash"


class Application(HabitatBase):
    def __init__(self, forest=None, filename=None, parent=None):
        if forest is None:
            forest = {}
        super(Application, self).__init__(
            forest=forest, filename=filename, parent=parent
        )

    def _init_variables(self):
        super(Application, self)._init_variables()
        self.aliases = NotSet

    @HabitatProperty
    def aliases(self):
        return self._aliases

    @aliases.setter
    def aliases(self, aliases):
        self._aliases = aliases

    def load(self, filename):
        data = super(Application, self).load(filename)
        self.aliases = data.get("aliases", NotSet)
        return data


class Config(HabitatBase):
    def _init_variables(self):
        super(Config, self)._init_variables()
        self.apps = NotSet
        self.inherits = NotSet

    @HabitatProperty
    def apps(self):
        return self._apps

    @apps.setter
    def apps(self, apps):
        self._apps = apps

    @HabitatProperty
    def inherits(self):
        return self._inherits

    @inherits.setter
    def inherits(self, inherits):
        self._inherits = inherits

    def load(self, filename):
        data = super(Config, self).load(filename)
        self.apps = data.get("apps", NotSet)
        self.inherits = data.get("inherits", NotSet)
        return data

    def reduced(self, resolver=None):
        """Returns a new instance with the final settings applied respecting inheritance"""
        return FlatConfig(self, resolver)


class FlatConfig(Config):
    def __init__(self, original_node, resolver):
        super(FlatConfig, self).__init__(original_node.forest)
        self.original_node = original_node
        self.filename = original_node.filename
        self.resolver = resolver
        self._context = original_node.context
        # Copy the properties from the inheritance system
        self._collect_values(self.original_node)

    def _collect_values(self, node, default=False):
        logger.debug("Loading node: {} inherits: {}".format(node.name, node.inherits))
        self._missing_values = False
        for attrname in self._properties:
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

    @property
    def fullpath(self):
        return self.separator.join([""] + [name for name in self.context])


class Placeholder(HabitatBase):
    """Provides an parent node for a child if one hasn't been created yet.
    This node will be replaced in the tree if a node is loaded for this position.
    """
