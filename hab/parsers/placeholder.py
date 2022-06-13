from . import HabBase


class Placeholder(HabBase):
    """Provides an parent node for a child if one hasn't been created yet.
    This node will be replaced in the tree if a node is loaded for this position.
    """


# This is the first place where both HabBase and its subclass Placeholder
# are defined, so this is where we have to set _placeholder.
HabBase._placeholder = Placeholder
