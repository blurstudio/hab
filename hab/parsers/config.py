import logging
import os

from .. import NotSet, utils
from ..errors import HabError, InvalidAliasError
from .hab_base import HabBase
from .meta import hab_property

logger = logging.getLogger(__name__)


class Config(HabBase):
    """The configuration for a given URI that defines required distros and environment
    variables need to be loaded if this config is chosen. This does not resolve `NotSet`
    values, see `FlatConfig` for the final resolved values that are actually applied."""

    def __init__(self, *args, **kwargs):
        self._alias_mods = NotSet
        super().__init__(*args, **kwargs)

    def _cache(self):
        return self.resolver.site.cache.config_paths(flat=True)

    @hab_property(process_order=120)
    def aliases(self):
        """Dict of the names and commands that need created to launch desired
        applications."""
        ret = self.frozen_data.get("aliases", {}).get(utils.Platform.name(), {})
        # Only return aliases if they are valid for the current verbosity
        return {k: v for k, v in ret.items() if self.check_min_verbosity(v)}

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

    def launch(self, alias_name, args=None, blocking=False, cls=None, **kwargs):
        """Launches the requested alias using subprocess.Popen.

        Args:
            alias_name (str): The alias name to run.
            args (list): Additional arguments for the command to be run by subprocess.
                This should be a list of each individual string argument. If a kwarg
                is being passed it should be passed as two items. ['--key', 'value'].
            blocking (bool or str, optional): Makes this method blocking by calling
                Popen.communicate. If a str value is used, is included in the call.
                The results of calling `proc.communicate` can be accessed from the
                `output_stdout` and `output_stderr` properties added to proc.
            cls (class, optional): A `subprocess.Popen` compatible class is
                initialized and used to run the alias. If not passed, then the
                site entry_point `hab.launch_cls` is used if defined. Otherwise the
                `hab.launcher.Launcher` class is used.
            **kwargs: Any keyword arguments are passed to subprocess.Popen. If on
                windows and using pythonw, prevents showing a command prompt.

        Returns:
            The created subprocess.Popen instance.
        """
        # Construct the command line arguments to execute
        if alias_name not in self.aliases:
            raise InvalidAliasError(alias_name, self)
        alias = self.aliases[alias_name]

        # Get the subprocess.Popen like class to use to launch the alias
        if cls is None:
            # Use the entry_point if defined on the alias
            alias_cls = alias.get("hab.launch_cls")
            if alias_cls:
                alias_cls = {"hab.launch_cls": alias_cls}
                eps = self.resolver.site.entry_points_for_group(
                    "hab.launch_cls", entry_points=alias_cls
                )
            else:
                # Otherwise use the global definition from Site
                eps = self.resolver.site.entry_points_for_group("hab.launch_cls")

            if eps:
                cls = eps[0].load()
            else:
                # Default to subprocess.Popen if not defined elsewhere
                from hab.launcher import Launcher

                cls = Launcher

        try:
            cmd = alias["cmd"]
        except KeyError:
            raise HabError(
                f'Alias "{alias_name}" does not have "cmd" defined'
            ) from None
        if isinstance(cmd, str):
            cmd = [cmd]
        if args:
            cmd.extend(args)

        # Apply the hab global and alias environment variable changes
        if "env" in kwargs:
            env = kwargs["env"]
        else:
            env = dict(os.environ)
        self.update_environ(env, alias_name)
        kwargs["env"] = env

        # Launch the subprocess using the requested Popen subclass
        logger.info(f"Launching: {cmd}")
        proc = cls(cmd, **kwargs)

        if blocking:
            if blocking is True:
                blocking = None
            proc.output_stdout, proc.output_stderr = proc.communicate(input=blocking)

        return proc

    def load(self, filename):
        data = super().load(filename)
        self._alias_mods = data.get("alias_mods", NotSet)
        self.inherits = data.get("inherits", NotSet)
        return data

    @hab_property(verbosity=1, group=0)
    def uri(self):
        # Mark uri as a HabProperty so it is included in _properties
        return super().uri
