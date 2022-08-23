from . import HabBase
from .meta import hab_property


class Placeholder(HabBase):
    """Provides an parent node for a child if one hasn't been created yet.
    This node will be replaced in the tree if a node is loaded for this position.
    """

    @hab_property(verbosity=2)
    def inherits(self):
        """Placeholders don't contain their own data, so they always inherit."""
        return True


# This is the first place where both HabBase and its subclass Placeholder
# are defined, so this is where we have to set _placeholder.
HabBase._placeholder = Placeholder
