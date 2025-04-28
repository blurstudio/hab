import json
import os
import shutil
from collections import namedtuple
from contextlib import contextmanager
from pathlib import Path, PurePath
from zipfile import ZipFile

import pytest
from jinja2 import Environment, FileSystemLoader
from packaging.requirements import Requirement

from hab import Resolver, Site

# Testing both cached and uncached every time adds extra testing time. This env
# var can be used to disable cached testing for local testing.
if os.getenv("HAB_TEST_UNCACHED_ONLY", "0") == "1":
    resolver_tests = ["uncached"]
else:
    resolver_tests = ["uncached", "cached"]


@pytest.fixture(scope="session")
def config_root():
    return Path(__file__).parent


def generate_habcached_site_file(config_root, dest):
    """Returns the path to a site config file generated from `site_main.json`
    configured so it can have a .habcache file generated next to it. The
    config_paths and distro_paths of the site file are hard coded to point to
    the repo's tests directory so it uses the same configs/distros. It also adds
    a `config-root` entry to `platform_path_maps`.
    """
    site_file = Path(dest) / "site.json"
    site_src = config_root / "site_main.json"

    # Load the site_main.json files contents so we can modify it before saving
    # it into the dest for testing.
    data = json.load(site_src.open())
    append = data["append"]

    # Hard code relative_root to the tests folder so it works from
    # a random testing directory without copying all configs/distros.
    for key in ("config_paths", "distro_paths"):
        for i in range(len(append[key])):
            append[key][i] = append[key][i].format(relative_root=site_src.parent)

    # Add platform_path_maps for the pytest directory to simplify testing and
    # test cross-platform support. We need to add all platforms, but this only
    # needs to run on the current platform, so add the same path to all.
    append["platform_path_maps"]["config-root"] = {
        platform: str(config_root) for platform in data["set"]["platforms"]
    }

    with site_file.open("w") as fle:
        json.dump(data, fle, indent=4, sort_keys=True)

    return site_file


@pytest.fixture(scope="session")
def habcached_site_file(config_root, tmp_path_factory):
    """Generates a site.json file and generates its habcache file.
    This file is stored in a `_cache` directory in the pytest directory.
    This persists for the entire testing session and can be used by other tests
    that need to test hab when it is using a habcache.
    """
    # Create the site file
    shared = tmp_path_factory.mktemp("_cache")
    ret = generate_habcached_site_file(config_root, shared)

    # Generate the habcache file
    site = Site([ret])
    resolver = Resolver(site)
    site.cache.save_cache(resolver, ret)

    return ret


@pytest.fixture
def habcached_resolver(habcached_site_file):
    """Returns a Resolver using a habcache file that was generated for this session.

    See the `habcached_site_file` fixture for details on how the cache is setup.
    For ease of testing the path to the saved habcache file is stored in
    `_test_cache_file` on the returned resolver.
    """
    site = Site([habcached_site_file])
    resolver = Resolver(site)
    # Generate the cache and provide easy access to the habcache file path
    resolver._test_cache_file = site.cache.site_cache_path(habcached_site_file)

    return resolver


@pytest.fixture
def uncached_resolver(config_root):
    """Return a standard testing resolver not using any habcache files."""
    site = Site([config_root / "site_main.json"])
    return Resolver(site=site)


@pytest.fixture(params=resolver_tests)
def resolver(request):
    """Returns a hab.Resolver instance using the site_main.json site config file.

    This is a parameterized fixture that returns both cached and uncached versions
    of the `site_main.json` site configuration. Note the cached version uses a
    copy of it stored in the `_cache0` directory of the pytest temp files. This
    should be used for most tests to ensure that all features are tested, but if
    the test is not affected by caching you can use `uncached_resolver` instead.
    """
    test_map = {"uncached": "uncached_resolver", "cached": "habcached_resolver"}
    return request.getfixturevalue(test_map[request.param])


Distro = namedtuple("Distro", ["name", "version", "inc_version", "distros"])


class DistroInfo(namedtuple("DistroInfo", ["root", "versions", "zip_root"])):
    default_versions = (
        ("dist_a", "0.1", True, None),
        ("dist_a", "0.2", False, ["dist_b"]),
        ("dist_a", "1.0", False, None),
        ("dist_b", "0.5", False, None),
        ("dist_b", "0.6", False, None),
    )

    @classmethod
    def dist_version(cls, distro, version):
        return f"{distro}_v{version}"

    @classmethod
    def hab_json(cls, distro, version=None, distros=None):
        data = {"name": distro}
        if version:
            data["version"] = version
        if distros:
            data["distros"] = distros
        return json.dumps(data, indent=4)

    @classmethod
    def generate(cls, root, versions=None, zip_created=None, zip_root=None):
        if versions is None:
            versions = cls.default_versions
        if zip_root is None:
            zip_root = root

        versions = {(x[0], x[1]): Distro(*x) for x in versions}

        for version in versions.values():
            name = cls.dist_version(version.name, version.version)
            filename = root / f"{name}.zip"
            ver = version.version if version.inc_version else None
            with ZipFile(filename, "w") as zf:
                # Make the .zip file larger than the remotezip initial_buffer_size
                # so testing of partial archive reading is forced use multiple requests
                zf.writestr("data.txt", "-" * 64 * 1024)
                zf.writestr(
                    ".hab.json",
                    cls.hab_json(version.name, version=ver, distros=version.distros),
                )
                zf.writestr("file_a.txt", "File A inside the distro.")
                zf.writestr("folder/file_b.txt", "File B inside the distro.")
                if zip_created:
                    zip_created(zf)

        # Create a correctly named .zip file that doesn't have a .hab.json file
        # to test for .zip files that are not distros.
        with ZipFile(root / "not_valid_v0.1.zip", "w") as zf:
            zf.writestr("README.txt", "This file is not a hab distro zip.")

        return cls(root, versions, zip_root)


@pytest.fixture(scope="session")
def distro_finder_info(tmp_path_factory):
    """Returns a DistroInfo instance with extracted distros ready for hab.

    This is useful for using an existing hab distro structure as your download server.
    """
    root = tmp_path_factory.mktemp("_distro_finder")

    def zip_created(zf):
        """Extract all contents zip into a distro folder structure."""
        filename = Path(zf.filename).stem
        distro, version = filename.split("_v")
        zf.extractall(root / distro / version)

    return DistroInfo.generate(root, zip_created=zip_created)


@pytest.fixture(scope="session")
def zip_distro(tmp_path_factory):
    """Returns a DistroInfo instance for a zip folder structure.

    This is useful if the zip files are locally accessible or if your hab download
    server supports `HTTP range requests`_. For example if you are using Amazon S3.

    .. _HTTP range requests:
       https://developer.mozilla.org/en-US/docs/Web/HTTP/Range_requests
    """
    root = tmp_path_factory.mktemp("_zip_distro_files")
    return DistroInfo.generate(root)


@pytest.fixture(scope="session")
def zip_distro_sidecar(tmp_path_factory):
    """Returns a DistroInfo instance for a zip folder structure with sidecar
    `.hab.json` files.

    This is useful when your hab download server does not support HTTP range requests.
    """
    root = tmp_path_factory.mktemp("_zip_distro_sidecar_files")

    def zip_created(zf):
        """Extract the .hab.json from the zip to a sidecar file."""
        filename = Path(zf.filename).stem
        sidecar = root / f"{filename}.hab.json"
        path = zf.extract(".hab.json", root)
        shutil.move(path, sidecar)

    return DistroInfo.generate(root, zip_created=zip_created)


@pytest.fixture(scope="session")
def _zip_distro_s3(tmp_path_factory):
    """The files used by `zip_distro_s3` only generated once per test."""
    root = tmp_path_factory.mktemp("_zip_distro_s3_files")
    bucket_root = root / "hab-test-bucket"
    bucket_root.mkdir()
    return DistroInfo.generate(bucket_root, zip_root=root)


@pytest.fixture()
def zip_distro_s3(_zip_distro_s3, monkeypatch):
    """Returns a DistroInfo instance for a s3 zip cloud based folder structure.

    This is used to simulate using an aws s3 cloud storage bucket to host hab
    distro zip files.
    """
    from cloudpathlib import implementation_registry
    from cloudpathlib.local import LocalS3Client, local_s3_implementation

    from hab.distro_finders import s3_zip

    monkeypatch.setitem(implementation_registry, "s3", local_s3_implementation)
    monkeypatch.setattr(s3_zip, "S3Client", LocalS3Client)
    return _zip_distro_s3


class Helpers(object):
    """A collection of reusable functions that tests can use."""

    @staticmethod
    def assert_requirements_equal(req, check):
        """Assert that a requirement dict matches a list of requirements.

        Args:
            req (dict): A Requirement dictionary matching the output of
                ``hab.solvers.Solvers.simplify_requirements``.
            check (list): A list of requirement strings. This takes a list
                so writing tests requires less boilerplate.

        Raises:
            AssertionError: If the provided req and check don't exactly match.
        """
        try:
            assert len(req) == len(check)
        except AssertionError:
            # Provide additional information to help debug a failing test. The simple
            # len assert doesn't make it easy to debug a failing test
            print(" Requirement dict ".center(50, "-"))
            print(req)
            print(" Check ".center(50, "-"))
            print(check)
            raise
        for chk in check:
            chk = Requirement(chk)
            assert Helpers.cmp_requirement(req[chk.name], chk)

    @staticmethod
    def check_path_list(paths, checks):
        """Casts the objects in both lists to PurePath objects so they can be
        reliably asserted and differences easily viewed in the pytest output.
        """
        paths = [PurePath(p) for p in paths]
        checks = [PurePath(p) for p in checks]
        assert paths == checks

    @staticmethod
    def cmp_requirement(a, b):
        """Convenience method to check if two Requirement objects are the same.

        Args:
            a (Requirement): The first Requirement to compare
            b (Requirement): The second Requirement to compare

        Returns:
            bool: If a and b represent the same requirement
        """
        return type(a) == type(b) and str(a) == str(b)

    @staticmethod
    @contextmanager
    def reset_environ():
        """Resets the environment variables once the with context exits."""
        old_environ = dict(os.environ)
        try:
            yield
        finally:
            # Restore the original environment variables
            os.environ.clear()
            os.environ.update(old_environ)

    @staticmethod
    def compare_files(generated, check):
        """Assert two files are the same with easy to read errors.

        First compares the number of lines for differences, then checks each line
        for differences raising an AssertionError on the first difference.

        Args:
            generated (pathlib.Path): The file generated for testing. This will
                have a newline added to the end to match the pre-commit enforced
                "fix end of files" check.
            check (pathlib.Path): Compare generated to this check file. It is
                normally committed inside the hab/tests folder.
        """
        _check = check.open().readlines()
        cache = generated.open().readlines()
        # Add trailing white space to match template file's trailing white space
        cache[-1] += "\n"
        cache_len = len(cache)
        check_len = len(_check)
        assert cache_len == check_len, (
            "Generated cache does not have the same number of lines "
            f'"{check.name}": "{generated}"'
        )

        for i in range(len(cache)):
            assert cache[i] == _check[i], (
                f"Difference in generated cache on line {i}: "
                f'"{check.name}" -> "{generated}"'
            )

    @staticmethod
    def render_template(template, dest, **kwargs):
        """Render a jinja template in from the test templates directory.

        Args:
            template (str): The name of the template file in the templates dir.
            dest (os.PathLike): The destination filename to write the output.
            **kwargs: All kwargs are used to render the template.
        """
        environment = Environment(
            loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        template = environment.get_template(template)

        text = template.render(**kwargs).rstrip() + "\n"
        with dest.open("w") as fle:
            fle.write(text)

    @classmethod
    def render_resolver(cls, site_template, dest, **kwargs):
        """Calls `render_template` and constructs a Resolver instance for it."""
        # Build the hab site
        site_file = dest / "site.json"
        cls.render_template(site_template, site_file, **kwargs)

        site = Site([site_file])
        return Resolver(site)


@pytest.fixture
def helpers():
    """Expose the Helpers class as a fixture for ease of use in tests."""
    return Helpers
