from typing import Any, List

from importlib_metadata import EntryPoint


class EntryPointNull(EntryPoint):
    """Represents a disabled entry point.

    This is used in `Site.entry_points_for_group(..., omit_none=False)` to represent
    a entry point being set to None/null. Otherwise the null entry point is omitted.

    Example host.json:

        {"append": {"entry_points": {"hab.cli": {"gui": null}}}}
    """

    def __init__(self, name: str, value: None, group: str) -> None:
        # Keeping `value` argument to preserve compatibility
        if value is not None:
            raise ValueError("The value must be None.")

        vars(self).update(name=name, value=None, group=group)

    def load(self) -> Any:
        return None

    @property
    def module(self) -> str:
        return "builtins"

    @property
    def attr(self) -> str:
        return ""

    @property
    def extras(self) -> List[str]:
        # Note: Python 3.7 requires using `List[str]` from typing
        return []
