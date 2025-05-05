from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

from .. import utils
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

        This respects `self.resolver.prereleases`, so pre-releases will only be
        returned if that is set to True or if this specification uses an
        "Inclusive ordered comparison"(`<=`, `>=`) and the specification
        contains any of the pre-release specifiers (`.dev1`). You will need
        to enable prereleases to use "Exclusive ordered comparison"(`<`, `>`)s.
        This is consistent with how pip handles these options.
        """
        if isinstance(specification, Requirement):
            specifier = specification.specifier
        elif isinstance(specification, SpecifierSet):
            specifier = specification
        else:
            specifier = Requirement(specification).specifier

        # If the specifier excludes all possible versions then it should be
        # considered invalid
        if not utils.specifier_valid(str(specifier)):
            raise InvalidRequirementError(
                f'Specifier for "{self.name}" excludes all possible '
                f'versions: "{specifier}"'
            )

        # If a pre-release specifier was provided, it should enable pre-releases
        # even if the site doesn't. This replicates explicitly passing a pre-release
        # version to pip even if you don't pass `--pre`.
        prereleases = self.resolver.prereleases or specifier.prereleases
        return specifier.filter(self.versions.keys(), prereleases=prereleases)

    @property
    def versions(self):
        """A dict of available distro versions"""
        return {c.version: c for c in self.children}
