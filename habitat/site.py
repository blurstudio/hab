import logging
import os
import sys
from collections import UserDict
from pathlib import Path

# from . import HabitatMeta, NotSet, habitat_property
from . import json
from .merge_dict import MergeDict

logger = logging.getLogger(__name__)


class Site(UserDict):
    def __init__(self, paths=None):
        self.data = {}

        if not paths:
            paths = os.getenv("HAB_PATHS", "").split(os.pathsep)
        self.paths = [Path(p) for p in paths if p]

        self.load()

    def load(self):
        """Iterates over each file in self.path. Replacing the value of each key.
        The last file in the list will have its settings applied even if other
        files define them."""
        for path in self.paths:
            self.load_file(path)

    def load_file(self, filename):
        logger.debug('Loading "{}"'.format(filename))
        with open(filename, "r") as fle:
            try:
                data = json.load(fle)
            except ValueError as e:
                # Include the filename in the traceback to make debugging easier
                msg = '{} Filename: "{}"'.format(e, filename)
                raise type(e)(msg, e.doc, e.pos).with_traceback(sys.exc_info()[2])

        merger = MergeDict(relative_root=filename.parent)
        merger.update(self, data)

    @property
    def paths(self):
        return self._paths

    @paths.setter
    def paths(self, paths):
        self._paths = paths


# Don't allow configurations to overwrite these values.
Site._reserved_keys = set(dir(Site))


# class Site(object, metaclass=HabitatMeta):
#     def __init__(self, paths=None):
#         self.paths = paths if paths else os.getenv("HAB_PATHS", "").split(os.pathsep)
#         self._config_paths = []
#         self._distro_paths = []

#         self.load()

#     def load(self):
#         for path in self.paths:
#             self.load_file(path)

#     def load_file(self, filename):
#         logger.debug('Loading "{}"'.format(filename))
#         with open(filename, "r") as fle:
#             try:
#                 data = json.load(fle)
#                 # TODO: update __dict__ with the contents of this value instead?
#             except ValueError as e:
#                 # Include the filename in the traceback to make debugging easier
#                 msg = '{} Filename: "{}"'.format(e, filename)
#                 raise type(e)(msg, e.doc, e.pos).with_traceback(sys.exc_info()[2])

#         for prop in self._properties:
#             value = data.get(prop, NotSet)
#             logger.debug(f'Setting "{prop}" to {value}')
#             if value is not NotSet:
#                 setattr(self, prop, value)

#     @habitat_property()
#     def config_paths(self):
#         return self._config_paths

#     @config_paths.setter
#     def config_paths(self, paths):
#         self._config_paths = paths

#     @habitat_property()
#     def distro_paths(self):
#         return self._distro_paths

#     @distro_paths.setter
#     def distro_paths(self, paths):
#         self._distro_paths = paths
