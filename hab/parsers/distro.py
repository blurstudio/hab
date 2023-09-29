from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

from ..errors import InvalidRequirementError
from .hab_base import HabBase


class Distro(HabBase):
    """Container of DistroVersion objects. One per distro exists in a distro forest"""

    def latest_version(self, specifier):
        """Returns the newest version available matching the specifier"""
        versions = self.matching_versions(specifier)
        try:
            version = max(versions)
        except ValueError:
            raise InvalidRequirementError(
                f'Unable to find a valid version for "{specifier}" in versions '
                f'[{", ".join([str(v) for v in self.versions.keys()])}]'
            ) from None
        return self.versions[version]

    def matching_versions(self, specification):
        """Returns a list of versions available matching the version specification.
        See `packaging.requirements` for details on valid requirements, but it
        should be the same as pip requirements.
        """
        if isinstance(specification, Requirement):
            specifier = specification.specifier
        elif isinstance(specification, SpecifierSet):
            specifier = specification
        else:
            specifier = Requirement(specification).specifier
        return specifier.filter(
            self.versions.keys(), prereleases=self.resolver.prereleases
        )

    @property
    def versions(self):
        """A dict of available distro versions"""
        return {c.version: c for c in self.children}
