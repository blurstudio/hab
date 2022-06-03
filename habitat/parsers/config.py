from . import HabitatBase, NotSet, habitat_property


class Config(HabitatBase):
    def _init_variables(self):
        super(Config, self)._init_variables()
        self.inherits = NotSet

    @habitat_property(verbosity=2)
    def inherits(self):
        return self._inherits

    @inherits.setter
    def inherits(self, inherits):
        self._inherits = inherits

    def load(self, filename):
        data = super(Config, self).load(filename)
        self.inherits = data.get("inherits", NotSet)
        return data

    @habitat_property(verbosity=1, group=0)
    def uri(self):
        # Mark uri as a HabitatProperty so it is included in _properties
        return super(Config, self).uri
