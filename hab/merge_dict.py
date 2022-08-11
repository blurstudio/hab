import os

from . import utils


class MergeDict(object):
    def __init__(self, platform=None, **format_kwargs):
        self.format_kwargs = format_kwargs
        self.formatter = self.default_format
        self.pathsep = os.pathsep
        # self.platform = platform
        self.platform = 'windows'
        self.validator = None

    def default_format(self, value):
        if isinstance(value, list):
            # Format the individual items if a list of args is used.
            # return [v.format(**self.format_kwargs) for v in value]
            return [self.default_format(v) for v in value]
        if isinstance(value, bool):
            return value
        return value.format(**self.format_kwargs)

    @property
    def format_kwargs(self):
        return self._format_kwargs

    @format_kwargs.setter
    def format_kwargs(self, value):
        self._format_kwargs = value
        self._format_kwargs_cleaned = {
            k: utils.path_forward_slash(v) for k, v in value.items()
        }

    def join(self, a, b):
        """Join the two inputs into a flat list. If an input is a string it
        is split by ``self.pathsep``.

        Args:
            a: ``b`` is added after this.
            b: ``a`` is added before this.

        Returns:
            list: The joined a and b values.
        """
        if isinstance(a, str):
            a = a.split(self.pathsep)
        if isinstance(b, str):
            b = b.split(self.pathsep)

        return a + b

    def update(self, base, changes):
        """Check and update environment with the provided environment config."""

        # If os_specific is specified, we are defining environment variables per-os
        # not globally. Lookup the current os's configuration.
        if changes.get("os_specific", False):
            changes = changes.get(self.platform, {})

        if self.validator:
            self.validator(changes)

        if "unset" in changes:
            # When applying the env vars later None will trigger removing the env var.
            # The other operations may end up replacing this value.
            base.update({key: None for key in changes["unset"]})

        # set, prepend, append are all treated as set operations, this lets us override
        # base user and system variable values without them causing issues.
        if "set" in changes:
            for key, value in changes["set"].items():
                base[key] = self.formatter(value)
                if isinstance(base[key], str):
                    base[key] = [base[key]]

        for operation in ("prepend", "append"):
            if operation not in changes:
                continue

            for key, value in changes[operation].items():
                existing = base.get(key, "")
                if existing:
                    if operation == "prepend":
                        value = self.join(value, existing)
                    else:
                        value = self.join(existing, value)
                else:
                    # Convert value into a list if it isn't one
                    value = self.join(value, [])
                base[key] = self.formatter(value)
