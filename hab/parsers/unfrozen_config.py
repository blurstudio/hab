import logging
from copy import deepcopy

from .. import NotSet
from .config import Config
from .meta import hab_property

logger = logging.getLogger(__name__)


class UnfrozenConfig(Config):
    def __init__(self, frozen_data, resolver, uri=NotSet, forest=None):
        super().__init__(None, resolver)
        self.frozen_data = deepcopy(frozen_data)

        # Restore the HAB_URI env variable that was removed during freeze
        for platform in self.frozen_data.setdefault("environment", {}):
            self.frozen_data["environment"][platform].setdefault(
                "HAB_URI", self.frozen_data["uri"]
            )

    @classmethod
    def _dump_versions(cls, value, verbosity=0, color=None):
        """Returns the version information for this object as a list of strings."""
        # Frozen versions are already a list of strings
        return sorted(value)

    # Note: 'alias_mods' needs to be processed before 'environment'
    @hab_property(verbosity=None, process_order=50)
    def alias_mods(self):
        """Returns NotSet. Any alias_mods have already been baked into aliases."""
        return NotSet

    @hab_property(verbosity=2)
    def inherits(self):
        """Returns False. Unfrozen configurations can not inherit from other configs."""
        return False

    @property
    def fullpath(self):
        return self.frozen_data["uri"]

    @property
    def uri(self):
        return self.frozen_data["uri"]

    @hab_property(verbosity=1)
    def versions(self):
        return self.frozen_data.get("versions", [])
