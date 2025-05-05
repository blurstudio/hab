from .. import NotSet
from .distro import Distro
from .meta import hab_property
from .placeholder import Placeholder


class StubDistroVersion(Placeholder):
    """A specific version of the loaded `Distro`'s. Including its requirements,
    aliases and environment variables."""

    _context_method = "name"
    _placeholder = Distro

    def __init__(self, forest, resolver, name):
        super().__init__(forest=forest, resolver=resolver)
        self.distro_name = name
        self.name = f"{name}==STUB"
        self.context = [name]
        self.version = "0+stub"

    @hab_property()
    def aliases(self):
        return NotSet

    @hab_property()
    def alias_mods(self):
        return {}
