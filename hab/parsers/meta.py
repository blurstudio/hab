class _HabProperty(property):
    """The @property decorator that can be type checked by the `HabMeta` metaclass

    Any properties using this decorator will have their name added to `_properties`.
    Don't use this class directly, use the hab_property decorator instead.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Copy from the class, and store it on the instance. This makes it so we
        # can use isinstance checks against this class.
        cls = type(self)
        self.group = cls.group
        self.process_order = cls.process_order
        self.verbosity = cls.verbosity

    def sort_key(self):
        """Used to provide consistent and controlled when dynamically processing
        _HabProperties.
        """
        return (self.process_order, self.fget.__name__)


def hab_property(verbosity=0, group=1, process_order=100):
    """Decorate this function as a property and configure how it shows up in the dump.

    Args:
        verbosity (int, optional): Specify the minimum verbosity required to show.
            Setting this to None will remove it from the dump. This is useful to
            hide a property that is needed in a super-class but not a subclass.
        group (int, optional): Controls how dump sorts the results. The sort uses
            (group, name) as its sort key, so common group values are sorted
            alphabetically. This should rarely be used and only 0 or 1 should be used
            to reduce the complexity of finding the property you are looking for.
        process_order (int, optional): Fine control over the order properties are
            processed in. The sort uses (process_order, name) as its sort key, so
            common process_order values are sorted alphabetically. This should only
            be needed in specific cases. This is used by ``_HabProperty.sort_key``.
    """
    # Store the requested values to the class so __init__ can copy them into its
    # instance when initialized by the decoration process.
    _HabProperty.group = group
    _HabProperty.process_order = process_order
    _HabProperty.verbosity = verbosity
    return _HabProperty


class HabMeta(type):
    """Scans for HabProperties and adds their name to the `_properties` dict."""

    def __new__(cls, name, bases, dct):  # noqa: B902
        desc = {}
        # Include any _properties that are added by base classes we are inheriting.
        for base in bases:
            if hasattr(base, "_properties"):
                desc.update(base._properties)

        # Add any new _properties defined on this class
        for k, v in dct.items():
            if isinstance(v, _HabProperty):
                desc[k] = v
        dct["_properties"] = desc
        return type.__new__(cls, name, bases, dct)
