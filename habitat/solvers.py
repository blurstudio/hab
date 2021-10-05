from __future__ import print_function
from copy import copy
import logging
from .errors import MaxRedirectError
from packaging.requirements import Requirement

logger = logging.getLogger(__name__)


class Solver(object):
    """Recursively check requirements into a flat set of requirements that satisfy the
    requirements and their requirements, etc.

    Args:
        requirements (list): The requirements to process and store in resolved.
        resolver (habitat.Resolver): The Resolver used to define all distros and versions.

    Attributes:
        invalid (dict, optional): If a recursive requirement makes a already resolved
            version invalid, that version is added to this list as an exclusive exclude.
    """

    def __init__(self, requirements, resolver):
        self.invalid = {}
        self.max_redirects = 2
        self.requirements = requirements
        self.resolver = resolver
        self.redirects_required = 0

    @classmethod
    def _append_requirement(cls, requirements, req):
        """Combines any existing Requirement specifier with the new specifier.

        Args:
            requirements (dict): A dictionary of the requirements to modify.
            req (packaging.requirements.Requirement): The requirement to be combined
                with any existing requirement in requirements.

        Returns:
            The updated Requirement object that is also stored in requirements.
        """
        if not isinstance(req, Requirement):
            req = Requirement(req)  # pragma: no cover

        name = req.name
        if name in requirements:
            requirements[name].specifier &= req.specifier
        else:
            requirements[name] = copy(req)
        return requirements[name]

    def _resolve(
        self,
        requirements,
        resolved=None,
        processed=None,
    ):
        """Recursively solve the provided requirements into a final list of requirements.

        Args:
            requirements (list): The requirements to process and store in resolved.
            resolved (dict): This dictionary is used to store the final resolved
                requirements matching the requested requirements.
            processed (set, optional): A set of `habitat.parsers.DistroVersion`
                objects that have already been resolved. This prevents re-processing
                the same version over and over.

        Raises:
            ValueError: "Removing invalid version ..." This error indicates the need
                to re-run `_resolve`. A version added to the requirements that was later
                found to be no longer valid. A explicit `!=` version requirement has
                been added to `invalid` so calling `_resolve` again will prevent using
                that version for future dependency resolution.
        """

        # Set the default value for mutable objects
        if processed is None:
            processed = set()
        if resolved is None:
            resolved = {}

        logger.debug("Requirements: {}".format(requirements))
        for req in requirements:
            # Update the requirement to match all current requirements
            req = self._append_requirement(resolved, req)
            name = req.name
            if name in self.invalid:
                # TODO: build the correct not specifier
                invalid = self.invalid[name]
                logger.debug("Adding invalid specifier: {}".format(invalid))
                req = req.specifier & invalid.specifier

            logger.debug("Checking requirement: {}".format(req))
            # Attempt to find a version, raises a exception if no version was found
            version = self.resolver.distros[name].latest_version(req)
            logger.debug("Found Version: {}".format(version.name))
            if version.distros and version not in processed:
                # Check if updated requirements have forced us to re-evaluate
                # our requirements.
                for v in processed:
                    if v.distro_name == version.distro_name:
                        invalid = Requirement("{}!={}".format(v.distro_name, v.version))
                        self._append_requirement(self.invalid, invalid)
                        raise ValueError(
                            "Removing invalid version {}".format(version.name)
                        )

                processed.add(version)
                self._resolve(version.distros, resolved, processed)

        return resolved

    def resolve(self):
        """Recursively solve the provided requirements into a final list of requirements.

        Args:
            requirements (list): The requirements to process and store in resolved.
            resolved (dict): This dictionary is used to store the final resolved
                requirements matching the requested requirements.
            processed (set, optional): A set of `habitat.parsers.DistroVersion`
                objects that have already been resolved. This prevents re-processing
                the same version over and over.

        Raises:
            MaxRedirectError: Redirect limit reached, unable to resolve the requested
                requirements.
        """

        self.redirects_required = 0
        logger.info("Resolving requirements: {}".format(self.requirements))
        while True:
            logger.info(
                "Attempt {} at resolving requirements".format(
                    self.redirects_required + 1
                )
            )
            try:
                return self._resolve(self.requirements)
            except ValueError as error:
                logger.info(str(error))
                self.redirects_required += 1
                if self.redirects_required >= self.max_redirects:
                    raise MaxRedirectError(
                        "Redirect limit of {} reached".format(self.max_redirects)
                    )
