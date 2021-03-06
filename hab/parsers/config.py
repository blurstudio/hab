from . import HabBase, NotSet, hab_property


class Config(HabBase):
    """The configuration for a given URI that defines required distros and environment
    variables need to be loaded if this config is chosen. This does not resolve `NotSet`
    values, see `FlatConfig` for the final resolved values that are actually applied."""

    def _init_variables(self):
        super(Config, self)._init_variables()
        self.inherits = NotSet

    @hab_property(verbosity=2)
    def inherits(self):
        return self._inherits

    @inherits.setter
    def inherits(self, inherits):
        self._inherits = inherits

    def load(self, filename):
        data = super(Config, self).load(filename)
        self.inherits = data.get("inherits", NotSet)
        return data

    @hab_property(verbosity=1, group=0)
    def uri(self):
        # Mark uri as a HabProperty so it is included in _properties
        return super(Config, self).uri
