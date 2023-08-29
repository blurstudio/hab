from .. import NotSet
from .hab_base import HabBase
from .meta import hab_property


class Config(HabBase):
    """The configuration for a given URI that defines required distros and environment
    variables need to be loaded if this config is chosen. This does not resolve `NotSet`
    values, see `FlatConfig` for the final resolved values that are actually applied."""

    def __init__(self, *args, **kwargs):
        self._alias_mods = NotSet
        super().__init__(*args, **kwargs)

    # Note: 'alias_mods' needs to be processed before 'environment'
    @hab_property(verbosity=3, process_order=50)
    def alias_mods(self):
        """Dict of modifications that need to be made on aliases.
        These are used to modify the original configuration of an alias by another
        distro or config. This allows a plugin to add an environment variable to
        a specific alias even though the alias is defined by another distro/config.
        """
        return self._alias_mods

    @hab_property(verbosity=2)
    def inherits(self):
        return self.frozen_data.get("inherits", NotSet)

    @inherits.setter
    def inherits(self, inherits):
        self.frozen_data["inherits"] = inherits

    def load(self, filename):
        data = super().load(filename)
        self._alias_mods = data.get("alias_mods", NotSet)
        self.inherits = data.get("inherits", NotSet)
        return data

    @hab_property(verbosity=1, group=0)
    def uri(self):
        # Mark uri as a HabProperty so it is included in _properties
        return super().uri
