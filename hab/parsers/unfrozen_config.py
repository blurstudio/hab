import logging
from copy import deepcopy

from .. import NotSet
from .config import Config
from .meta import hab_property

logger = logging.getLogger(__name__)


class UnfrozenConfig(Config):
    def __init__(self, frozen_data, resolver, uri=NotSet, forest=None):
        super(UnfrozenConfig, self).__init__(None, resolver)
        self.frozen_data = deepcopy(frozen_data)

    @classmethod
    def _dump_versions(cls, value, verbosity=0, color=None):
        """Returns the version information for this object as a list of strings."""
        # Frozen versions are already a list of strings
        return sorted(value)

    @hab_property()
    def aliases(self):
        """List of the names and commands that need created to launch desired
        applications."""
        return self.frozen_data.get("aliases", {}).get(self._platform, [])

    @property
    def fullpath(self):
        return self.frozen_data["uri"]

    @property
    def uri(self):
        return self.frozen_data["uri"]

    @hab_property(verbosity=1)
    def versions(self):
        return self.frozen_data["versions"]
