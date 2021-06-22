from __future__ import print_function
import anytree
from future.utils import with_metaclass
import json
import logging
from packaging.version import Version
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
        self.filename = None
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
        self.environment = NotSet
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

    def dump(self):
        """Return a string of the properties and their values"""
        ret = []
        for prop in sorted(self._properties):
            value = getattr(self, prop)
            if value is NotSet:
                value = "<NotSet>"
            ret.append((prop, value))
        return tabulate.tabulate(ret)

    @HabitatProperty
    def environment(self):
        return self._environment

    @environment.setter
    def environment(self, env):
        self._environment = env

    @property
    def fullpath(self):
        return self.separator.join([""] + [node.name for node in self.path])

    def load(self, filename):
        self.filename = filename
        with open(filename, "r") as fle:
            data = json.load(fle)
        self.name = data["name"]
        self.requires = data.get("requires", NotSet)
        if "version" in data:
            self.version = Version(data.get("version"))
        self.environment = data.get("environment", NotSet)
        self.context = data.get("context", NotSet)

        return data

    @HabitatProperty
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    def reduced(self):
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
        self.aliases = data.get("aliases")
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
        self.apps = data.get("apps")
        self.inherits = data.get("inherits")
        return data


class FlatConfig(Config):
    def __init__(self, original_node, resolver):
        super(FlatConfig, self).__init__(original_node.forest)
        self.original_node = original_node
        self.resolver = resolver
        self._context = original_node.context
        # Copy the properties from the inheritance system

    def _collect_values(self, node, default=False):
        logger.debug("Loading node: {} inherits: {}".format(node.name, node.inherits))
        missing_values = False
        for attrname in self._properties:
            value = getattr(node, attrname)
            if value is NotSet:
                missing_values = True
            else:
                setattr(self, attrname, value)
        if node.inherits and missing_values:
            ancestors = node.ancestors
            if ancestors:
                return self._collect_values(ancestors[-1], default=default)
            elif not default and "default" in self.forest:
                # Start processing the default setup
                default = True
                # TODO: Figure out how to find the default closest_config
                default_node = self.resolver.closest_config(node.fullpath)
                self._collect_values(default_node, default=default)
        return missing_values

    @property
    def fullpath(self):
        return self.separator.join([""] + [name for name in self.context])


class Placeholder(HabitatBase):
    """Provides an parent node for a child if one hasn't been created yet.
    This node will be replaced in the tree if a node is loaded for this position.
    """
