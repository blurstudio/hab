import logging
import shutil
from pathlib import Path

from .. import NotSet
from ..errors import InstallDestinationExistsError
from .distro_version import DistroVersion

logger = logging.getLogger(__name__)


class DistroPath:
    __slots__ = ("distro", "hab_filename", "root", "site")

    def __init__(self, distro, root, relative=NotSet, site=None):
        self.distro = distro
        self.site = site
        if isinstance(root, str):
            root = Path(root)

        if relative is NotSet:
            if site and "relative_path" in site.downloads:
                relative = site.downloads["relative_path"]
            else:
                relative = "{distro_name}/{version}"

        if relative:
            root = root / relative.format(
                name=self.distro.name,
                distro_name=self.distro.distro_name,
                version=self.distro.version,
            )

        self.hab_filename = root / ".hab.json"
        self.root = root


class LazyDistroVersion(DistroVersion):
    """A DistroVersion class that loads data on first access.

    This class will raise a ValueError if filename is passed. This class expects
    that after initializing you set the properties `name`, `version`, `finder`,
    and `distro_name` After that you should call `load(filename)`.

    TODO: Add overrides to each getter/setter on this class like we have done to
    the distros property.
    """

    def __init__(self, *args, **kwargs):
        if len(args) > 2 or "filename" in kwargs:
            raise ValueError("Passing filename to this class is not supported.")

        self._loaded = False
        self._loaded_data = NotSet
        super().__init__(*args, **kwargs)

    @DistroVersion.distros.getter
    def distros(self):
        """A list of all of the requested distros to resolve."""
        self._ensure_loaded()
        return super().distros

    def install(self, dest, replace=False, relative=NotSet):
        """Install the distro into dest.

        Installs the distro into `dest / relative` creating any intermediate
        directories needed. In most cases you would pass one of your site's
        `distro_paths` to `dist` and the default relative value creates the
        recommended distro/version/contents folder structure that ensures that
        each distro version doesn't conflict with any others.

        Args:
            dest (pathlib.Path or str): The base directory to install this distro
                into. This is joined with `relative` to create the full path.
            replace (bool, optional): If dest already contains this distro, this
                will remove the existing install then re-install the distro.
            relative (str, optional): Additional path items joined to dest after
                being formatted. The kwargs "name", "distro_name" and "version"
                are passed to the `str.format` called on this variable.

        Raises:
            hab.errors.InstallDestinationExistsError: If the requested dest already
                contains this distro this error is raised and it is not installed.
                Unless `replace` is set to True.
        """
        if not isinstance(dest, DistroPath):
            dest = DistroPath(self, dest, relative=relative, site=self.resolver.site)

        installed = self.installed(dest, relative=relative)
        if installed:
            if not replace:
                raise InstallDestinationExistsError(dest.root)
            # Replace requested, remove the existing files before continuing.
            logger.info(f"Removing existing distro install: {dest.root}")
            shutil.rmtree(dest.root)

        self.finder.install(self.filename, dest.root)
        # The resolver cache is now out of date, force it to refresh on next access.
        self.resolver.clear_caches()

    def installed(self, dest, relative=NotSet):
        if not isinstance(dest, DistroPath):
            dest = DistroPath(self, dest, relative=relative, site=self.resolver.site)
        return dest.hab_filename.exists()

    def _ensure_loaded(self):
        """Ensures the data is loaded.

        On first call this method actually processes the loading of data for
        this DistroVersion. Any additional calls are ignored.
        """
        if self._loaded:
            return

        self._loaded = True
        data = self.finder.load_path(self.filename)
        return super().load(self.filename, data=data)

    def load(self, filename, data=NotSet):
        # The name should be the version == specifier.
        self.name = f"{self.distro_name}=={self.version}"

        self.filename = filename
        self._loaded_data = data
        self._loaded = False
        self.context = [self.distro_name]
        return data
