import logging
from copy import copy

from packaging.requirements import Requirement

from .errors import InvalidRequirementError, MaxRedirectError

logger = logging.getLogger(__name__)


class Solver(object):
    """Recursively check requirements into a flat set of requirements that satisfy the
    requirements and their requirements, etc.

    Args:
        requirements (list): The requirements to process and store in resolved.
        resolver (hab.Resolver): The Resolver used to define all distros and versions.
        forced (dict, optional): Forces this distro requirement replacing any resolved
            requirements. Using this may lead to configuring your environment
            incorrectly, use with caution.
        omittable (list, optional): A list of distro names that are not required.
            If a suitable distro can not be found, normally an `InvalidRequirementError`
            is raised. If that distro name is in this list a warning is logged instead.

    Attributes:
        invalid (dict, optional): If a recursive requirement makes a already resolved
            version invalid, that version is added to this list as an exclusive exclude.
    """

    def __init__(self, requirements, resolver, forced=None, omittable=None):
        self.forced = forced if forced else {}
        self.omittable = omittable if omittable else []
        self.invalid = {}
        self.max_redirects = 2
        self.requirements = requirements
        self.resolver = resolver
        self.redirects_required = 0

    @classmethod
    def append_requirement(cls, requirements, req):
        """Combines any existing Requirement specifier with the new specifier.

        Args:
            requirements (dict): A dictionary of the requirements to modify.
            req (packaging.requirements.Requirement): The requirement to be combined
                with any existing requirement in requirements.

        Returns:
            The updated Requirement object that is also stored in requirements.
        """
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
        reported=None,
    ):
        """Recursively solve the provided requirements into a final list of requirements.

        Args:
            requirements (list): The requirements to process and store in resolved.
            resolved (dict): This dictionary is used to store the final resolved
                requirements matching the requested requirements.
            processed (set, optional): A set of `hab.parsers.DistroVersion`
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
        if reported is None:
            reported = set()
        if resolved is None:
            resolved = {}

        # Make sure we process the forced requirements
        if self.forced:
            # Note: Make sure to preserve the order of requirements, ie OrderedDict.
            # This is mostly to ensure that tests for solver errors are not flaky.
            requirements = requirements.copy()
            requirements.update(self.forced)

        if requirements:
            reqs = requirements.values()
        else:
            # Support the possibility that no configuration defines requirements
            reqs = []
        logger.debug(f"Requirements: {reqs}")

        for req in reqs:
            name = req.name

            marker = req.marker
            if marker and not marker.evaluate():
                # If a marker is specified and its not valid for the current
                # system, skip this requirement.
                # https://packaging.pypa.io/en/stable/markers.html
                msg = f"Requirement ignored due to marker: {req}"
                if name in self.forced:
                    logger.critical(f"Forced {msg}")  # pragma: no cover
                else:
                    logger.warning(f"{msg}")
                continue

            if name in self.forced:
                if name in reported:
                    # Once we have processed this requirement, there is no need to
                    # re-process it, or log the warning again.
                    continue
                # If a distro requirement is forced, ignore the requested
                # requirement and instead resolve the forced requirement.
                req = self.forced[name]
                # This option should only be used for development and testing
                # always show a warning if its used.
                logger.warning(f"Forced Requirement: {req}")
                reported.add(name)

            if name in self.omittable and name not in self.resolver.distros:
                logger.warning(f"Skipping missing omitted requirement: {req}")
                continue

            # Update the requirement to match all current requirements
            req = self.append_requirement(resolved, req)
            if name in self.invalid:
                # TODO: build the correct not specifier
                invalid = self.invalid[name]
                logger.debug(f"Adding invalid specifier: {invalid}")
                req = req.specifier & invalid.specifier

            logger.debug(f"Checking requirement: {req}")

            # Attempt to find a version, raises a exception if no version was found
            try:
                dist = self.resolver.distros[name]
            except KeyError:
                raise InvalidRequirementError(
                    f"Unable to find a distro for requirement: {req}"
                ) from None
            version = dist.latest_version(req)
            logger.debug(f"Found Version: {version.name}")

            if version.distros and version not in processed:
                # Check if updated requirements have forced us to re-evaluate
                # our requirements.
                for v in processed:
                    if v.distro_name == version.distro_name:
                        invalid = Requirement(f"{v.distro_name}!={v.version}")
                        self.append_requirement(self.invalid, invalid)
                        raise ValueError(f"Removing invalid version {version.name}")

                processed.add(version)
                self._resolve(version.distros, resolved, processed, reported)

        return resolved

    def resolve(self):
        """Recursively solve the provided requirements into a final list of requirements.

        Args:
            requirements (list): The requirements to process and store in resolved.
            resolved (dict): This dictionary is used to store the final resolved
                requirements matching the requested requirements.
            processed (set, optional): A set of `hab.parsers.DistroVersion`
                objects that have already been resolved. This prevents re-processing
                the same version over and over.

        Raises:
            MaxRedirectError: Redirect limit reached, unable to resolve the requested
                requirements.
        """

        self.redirects_required = 0
        logger.info(f"Resolving requirements: {self.requirements}")
        while True:
            logger.info(
                f"Attempt {self.redirects_required + 1} at resolving requirements"
            )
            try:
                return self._resolve(self.requirements)
            except ValueError as error:
                logger.info(str(error))
                self.redirects_required += 1
                if self.redirects_required >= self.max_redirects:
                    raise MaxRedirectError(
                        f"Redirect limit of {self.max_redirects} reached"
                    ) from None

    @classmethod
    def simplify_requirements(cls, requirements):
        """Convert various requirement formats to the expected dict format.

        Ultimately only str or Requirement objects can be passed to this function, but
        it can flatten lists, tuples and dictionaries into a single dictionary where
        the key is the simple requirement name and the value is a Requirement object.

        if requirements is an dictionary, both the key and value are added to the
        requirements. The value can be a list of additional requirements to be included.

        If a requirement is defined more than once, append_requirement will be called
        to merge the specifiers together into a single requirement per name.

        Returns:
            dict: A dictionary with requirement names as keys and
                ``packaging.requirements.Requirement`` objects with all requested
                specifiers included.
        """
        ret = requirements

        if isinstance(requirements, (list, tuple)):
            ret = {}
            for req in requirements:
                if not isinstance(req, Requirement):
                    req = Requirement(req)
                cls.append_requirement(ret, req)

        elif isinstance(requirements, dict):
            ret = {}
            for key, value in requirements.items():
                if isinstance(value, list):
                    # If value is a list, add all of its values
                    for val in cls.simplify_requirements(value).values():
                        cls.append_requirement(ret, val)
                elif value:
                    if not isinstance(value, Requirement):
                        value = Requirement(value)
                    cls.append_requirement(ret, value)

                # Add the key as a requirement even if an value was specified
                if key:
                    if not isinstance(key, Requirement):
                        key = Requirement(key)
                    cls.append_requirement(ret, key)

        return ret
