from .. import NotSet
from .hab_base import HabBase
from .meta import hab_property


class Config(HabBase):
    """The configuration for a given URI that defines required distros and environment
    variables need to be loaded if this config is chosen. This does not resolve `NotSet`
    values, see `FlatConfig` for the final resolved values that are actually applied."""

    @hab_property(verbosity=2)
    def inherits(self):
        return self.frozen_data.get("inherits", NotSet)

    @inherits.setter
    def inherits(self, inherits):
        self.frozen_data["inherits"] = inherits

    def load(self, filename):
        data = super().load(filename)
        self.inherits = data.get("inherits", NotSet)
        return data

    @hab_property(verbosity=1, group=0)
    def uri(self):
        # Mark uri as a HabProperty so it is included in _properties
        return super().uri
