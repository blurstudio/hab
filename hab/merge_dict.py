import os

from . import utils


class MergeDict(object):
    def __init__(self, platform=None, platforms=("linux", "windows"), **format_kwargs):
        self.format_kwargs = format_kwargs
        self.formatter = self.default_format
        self.pathsep = os.pathsep
        self.platforms = platforms
        self.validator = None

        if platform is None:
            platform = utils.platform()
        self.platform = platform

    def apply_platform_wildcards(self, data, output=None):
        """Ensure the data dict is platform specific and any wildcard entries
        are applied to all of self.platforms.

        Args:
            data (dict): A dictionary of settings to apply. `make_os_specific`
                is called on it.
            output (dict, optional): If provided, the dictionary is updated in
                with the info stored in data. If not, a new dictionary is
                created and returned.

        Returns:
            dict: The modified dictionary. If output was provided it is the
                same object, if not a new dict is returned.
        """
        data = self.make_os_specific(data)

        if output is None:
            output = {"os_specific": True}

        for platform in self.platforms:
            platform_data = output.setdefault(platform, {})

            if "*" in data:
                self.update_platform(platform_data, data["*"])

            if platform in data:
                self.update_platform(platform_data, data[platform])

        return output

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

    @classmethod
    def make_os_specific(cls, data):
        """Ensure the dict conforms to the "os_specific=True" specification.
        If os_specific is missing or not true, a new dict is returned with a
        copy of data stored under the "*" key with `os_specific` removed.

        Args:
            data (dict): The dict to make os_specific. The original dict is
                returned if it's already os_specific, otherwise a new dict is
                returned.

        Returns:
            dict: A dict that conforms to the "os_specific=True" format.
        """
        if not data.get("os_specific", False):
            # Remove os_specific if it was defined so we don't keep it on the
            # wildcard platform dict.
            data = data.copy()
            data.pop("os_specific", False)
            data = {'*': data}
            data["os_specific"] = True
        return data

    def update_platform(self, data, changes):
        if self.validator:
            self.validator(changes)

        if "unset" in changes:
            # When applying the env vars later None will trigger removing the env var.
            # The other operations may end up replacing this value.
            data.update({key: None for key in changes["unset"]})

        # set, prepend, append are all treated as set operations, this lets us override
        # base user and system variable values without them causing issues.
        if "set" in changes:
            for key, value in changes["set"].items():
                data[key] = self.formatter(value)
                if isinstance(data[key], str):
                    data[key] = [data[key]]

        for operation in ("prepend", "append"):
            if operation not in changes:
                continue

            for key, value in changes[operation].items():
                existing = data.get(key, "")
                if existing:
                    if operation == "prepend":
                        value = self.join(value, existing)
                    else:
                        value = self.join(existing, value)
                else:
                    # Convert value into a list if it isn't one
                    value = self.join(value, [])
                data[key] = self.formatter(value)
