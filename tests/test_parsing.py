import anytree
from hab import utils
from hab.errors import DuplicateJsonError
from hab.parsers import DistroVersion, Config, NotSet
import json
import ntpath
from packaging.version import Version
import pytest
import re
import sys


def test_distro_parse(config_root, resolver):
    """Check that a distro json can be parsed correctly"""
    forest = {}
    app = DistroVersion(forest, resolver)
    path = config_root / "distros" / "all_settings" / "0.1.0.dev1" / ".hab.json"
    app.load(path)
    check = json.load(path.open())

    assert "{name}=={version}".format(**check) == app.name
    assert Version(check["version"]) == app.version
    assert check["environment"] == app.environment_config

    assert check["aliases"] == app.aliases
    assert ["all_settings"] == app.context

    # Verify that if the json file doesn't have "version" defined it uses the
    # parent directory as its version.
    app = DistroVersion(forest, resolver)
    path = config_root / "distros" / "maya" / "2020.0" / ".hab.json"
    app.load(path)
    check = json.load(path.open())

    # tests\distros\maya\2020.0\.hab.json does not have "version"
    # defined. This allows us to test that DistroVersion will pull the
    # version number from the parent directory not the json file.
    assert "version" not in check
    assert app.version == Version("2020.0")


def test_distro_version_resolve(config_root, resolver, helpers, monkeypatch):
    """Check the various methods for DistroVersion.version to be populated."""

    # Test that `.hab_version.txt` is respected if it exists.
    forest = {}
    app = DistroVersion(forest, resolver)
    path = config_root / "distros_version" / "txt_file" / ".hab.json"
    app.load(path)
    assert app.version == Version("1.7")

    # Test that an error is raised if the version could not be determined
    path = config_root / "distros_version" / "not_scm" / ".hab.json"
    app = DistroVersion(forest, resolver)
    with pytest.raises(LookupError) as excinfo:
        app.load(path)
    assert str(excinfo.value).startswith("Hab was unable to determine")

    # Test that setuptools_scm is able to resolve the version.
    app = DistroVersion(forest, resolver)
    # This env var forces setuptools_scm to this version so we don't have to
    # create a git repo to test that get_version is called correctly.
    monkeypatch.setenv("SETUPTOOLS_SCM_PRETEND_VERSION", "1.9")

    app.load(path)
    assert app.version == Version("1.9")


def test_distro_version(resolver):
    """Verify that we find the expected version for a given requirement."""
    maya = resolver.distros["maya2020"]

    assert maya.latest_version("maya2020").name == "maya2020==2020.1"
    assert maya.latest_version("maya2020<2020.1").name == "maya2020==2020.0"


def test_config_parse(config_root, resolver, helpers):
    """Check that a config json can be parsed correctly"""
    forest = {}
    config = Config(forest, resolver)
    path = config_root / "configs" / "default" / "default.json"
    config.load(path)

    check = ["maya2020", "tikal", "brSkinBrush", "animBot", "houdini18.5", "hsite"]

    # We can't do a simple comparison of Requirement keys so check that these resolved
    helpers.assert_requirements_equal(config.distros, check)

    # Check that the forest was populated correctly
    assert set(forest.keys()) == set(["default"])
    assert forest["default"] == config


def test_config_parenting(config_root, resolver):
    """Check that a correct tree structure is generated especially when loaded
    in a incorrect order.
    """

    def repr_list(node):
        return [repr(x) for x in anytree.iterators.PreOrderIter(node)]

    forest = {}
    root_paths = set((config_root,))
    # Ensure the forest has multiple trees when processing
    shared_path = config_root / "configs" / "default" / "default.json"
    Config(forest, resolver, filename=shared_path, root_paths=root_paths)

    # Load the tree structure from child to parent to test that the placeholder system
    # works as expected
    Config(
        forest,
        resolver,
        filename=config_root
        / "configs"
        / "project_a"
        / "project_a_Sc001_animation.json",
        root_paths=root_paths,
    )
    check = [
        "hab.parsers.placeholder.Placeholder('project_a')",
        "hab.parsers.placeholder.Placeholder('project_a/Sc001')",
        "hab.parsers.config.Config('project_a/Sc001/Animation')",
    ]
    assert check == repr_list(forest["project_a"])

    # Check that a middle plcaeholder was replaced
    mid_level_path = config_root / "configs" / "project_a" / "project_a_Sc001.json"
    Config(forest, resolver, filename=mid_level_path, root_paths=root_paths)
    check[1] = "hab.parsers.config.Config('project_a/Sc001')"
    assert check == repr_list(forest["project_a"])

    # Check that a middle Config object is used not replaced
    Config(
        forest,
        resolver,
        filename=config_root / "configs" / "project_a" / "project_a_Sc001_rigging.json",
        root_paths=root_paths,
    )
    check.append("hab.parsers.config.Config('project_a/Sc001/Rigging')")
    assert check == repr_list(forest["project_a"])

    # Check that a root item is replaced
    top_level_path = config_root / "configs" / "project_a" / "project_a.json"
    Config(forest, resolver, filename=top_level_path, root_paths=root_paths)
    check[0] = "hab.parsers.config.Config('project_a')"
    assert check == repr_list(forest["project_a"])

    # Verify that the correct exceptions are raised if root duplicates are loaded
    with pytest.raises(DuplicateJsonError):
        Config(forest, resolver, filename=top_level_path, root_paths=root_paths)
    assert check == repr_list(forest["project_a"])

    # and at the leaf level
    with pytest.raises(DuplicateJsonError):
        Config(forest, resolver, filename=mid_level_path, root_paths=root_paths)
    assert check == repr_list(forest["project_a"])

    # Check that the forest didn't loose the default tree
    assert ["hab.parsers.config.Config('default')"] == repr_list(forest["default"])


def test_metaclass():
    assert set(DistroVersion._properties.keys()) == set(
        [
            "aliases",
            "distros",
            "environment",
            "environment_config",
            "name",
            "version",
        ]
    )
    assert set(Config._properties.keys()) == set(
        [
            "distros",
            "environment",
            "environment_config",
            "inherits",
            "name",
            "uri",
        ]
    )


def test_dump(resolver):
    line = "-LINE-"

    def standardize(txt):
        """Dump adds an arbitrary length border of -'s that makes str comparing
        hard. Replace it with a constant value."""
        return re.sub(r"^-+$", line, txt, flags=re.M)

    # Build the test data so we can generate the output to check
    # Note: using `repr([u"` so this test passes in python 2 and 3
    pre = ["name:  child", "uri:  not_set/child"]
    post = ["inherits:  True"]
    env = [
        "environment:  UNSET_VARIABLE:  None",
        "              TEST:  case",
        "              FMT_FOR_OS:  a{;}b;c:{PATH!e}{;}d",
    ]

    env_config = [
        "environment_config:  unset:  UNSET_VARIABLE",
        "                     set:  TEST:  case",
        "                           FMT_FOR_OS:  a{;}b;c:{PATH!e}{;}d",
    ]
    cfg = resolver.closest_config("not_set/child")
    header = f"Dump of {type(cfg).__name__}('{cfg.fullpath}')"

    # Check that both environments can be hidden
    result = cfg.dump(
        environment=False, environment_config=False, verbosity=2, color=False
    )
    check = [f'{header}\n{line}']
    check.extend(pre)
    check.extend(post)
    check.append(line)
    check = '\n'.join(check)
    assert standardize(result) == check

    # Check that both environments can be shown
    result = cfg.dump(
        environment=True, environment_config=True, verbosity=2, color=False
    )
    check = [f'{header}\n{line}']
    check.extend(pre)
    check.extend(env)
    check.extend(env_config)
    check.extend(post)
    check.append(line)
    check = '\n'.join(check)
    assert standardize(result) == check

    # Check that only environment can be shown
    result = cfg.dump(
        environment=True, environment_config=False, verbosity=2, color=False
    )
    check = [f'{header}\n{line}']
    check.extend(pre)
    check.extend(env)
    check.extend(post)
    check.append(line)
    check = '\n'.join(check)
    # Check that only environment_config can be shown
    result = cfg.dump(
        environment=False, environment_config=True, verbosity=2, color=False
    )
    check = [f'{header}\n{line}']
    check.extend(pre)
    check.extend(env_config)
    check.extend(post)
    check.append(line)
    check = '\n'.join(check)
    assert standardize(result) == check


def test_dump_flat(resolver):
    """Test additional dump settings for FlatConfig objects"""
    cfg = resolver.resolve("not_set/child")
    # Check that dump formats versions nicely
    check = re.compile(
        r'versions:  (?P<ver>maya2020==2020\.1)(?P<file>:  [\w:\\.\/-]+\.json)?'
    )
    # Versions are not shown with verbosity >= 1
    result = cfg.dump(color=False)
    assert not check.search(result)

    # Verbosity 2 shows just the version requirement
    result = cfg.dump(verbosity=2, color=False)
    match = check.search(result)
    assert match.group('file') is None
    assert match.group('ver') == u"maya2020==2020.1"

    # Verbosity 3 also shows the json file name
    result = cfg.dump(verbosity=3, color=False)
    match = check.search(result)
    assert match.group('file') is not None


def test_environment(resolver):
    # Check that the correct errors are raised
    cfg = resolver.closest_config("not_set/env_path_set")
    with pytest.raises(ValueError) as excinfo:
        cfg.environment
    assert (
        str(excinfo.value)
        == 'You can not use PATH for the set operation: "path_variable"'
    )

    cfg = resolver.closest_config("not_set/env_path_unset")
    with pytest.raises(ValueError) as excinfo:
        cfg.environment
    assert str(excinfo.value) == "You can not unset PATH"

    # Check environment variable resolving
    cfg = resolver.closest_config("not_set/env1")

    assert cfg.environment["APPEND_VARIABLE"] == ["append_value"]
    assert cfg.environment["MAYA_MODULE_PATH"] == ["MMP_Set"]
    assert cfg.environment["PREPEND_VARIABLE"] == ["prepend_value"]

    check = [
        "{relative_root}/prepend",
        "{relative_root}/set",
        "{relative_root}/append",
    ]
    relative_root = utils.path_forward_slash(cfg.dirname)
    check = [c.format(relative_root=relative_root) for c in check]

    assert cfg.environment["RELATIVE_VARIABLE"] == check
    assert cfg.environment["SET_RELATIVE"] == [
        "{relative_root}".format(relative_root=relative_root)
    ]
    assert cfg.environment["SET_VARIABLE"] == ["set_value"]
    assert cfg.environment["UNSET_VARIABLE"] is None
    assert cfg.environment["UNSET_VARIABLE_1"] is None

    # Check `cfg.environment is NotSet` resolves correctly
    cfg = resolver.closest_config("not_set")
    assert cfg.environment == {}

    # Ensure our tests cover the early out if the config is missing append/prepend
    cfg = resolver.closest_config("not_set/child")
    assert cfg.environment == {
        "TEST": ["case"],
        "FMT_FOR_OS": ["a{;}b;c:{PATH!e}{;}d"],
        u"UNSET_VARIABLE": None,
    }


def test_flat_config(resolver):
    ret = resolver.resolve("not_set/child")
    check = {
        "TEST": ["case"],
        "FMT_FOR_OS": ["a{;}b;c:{PATH!e}{;}d"],
        u"UNSET_VARIABLE": None,
    }

    assert ret.environment == check
    assert ret.environment == check
    assert ret.environment == check

    # Check for edge case where self._environment was reset if the config didn't define
    # environment, but the attached distros did.
    ret = resolver.resolve("not_set/no_env")
    assert list(ret.environment.keys()) == ["DCC_MODULE_PATH"]
    assert list(ret.environment.keys()) == ["DCC_MODULE_PATH"]


def test_invalid_config(config_root, resolver):
    """Check that if an invalid json file is processed, its filename is included in
    the traceback"""
    path = config_root / "invalid.json"

    # Resolve if we are using pyjson5 or the native json class
    native_json = False
    try:
        from pyjson5 import Json5Exception as _JsonException
    except ImportError:
        native_json = True
        from builtins import ValueError as _JsonException

    with pytest.raises(_JsonException) as excinfo:
        Config({}, resolver, filename=path)

    if native_json:
        # If built-in json was used, check that filename was appended to the message
        assert f'Filename("{path}")' in str(excinfo.value)
    else:
        # If pyjson5 was used, check that the filename was added to the result dict
        assert excinfo.value.result['filename'] == str(path)


def test_misc_coverage(resolver):
    """Test that cover misc lines not covered by the rest of the tests"""
    assert str(NotSet) == "NotSet"

    # Check that dirname is modified when setting a blank filename
    cfg = Config({}, resolver)
    cfg.filename = ""
    # both of these values should be set to ``Path(os.devnull)``
    assert str(cfg.filename) in ("nul", "/dev/null")
    assert str(cfg.dirname) in ("nul", "/dev/null")

    # String values are cast to the correct type
    cfg.version = "1.0"
    assert cfg.version == Version("1.0")

    # Loading a directory raises a FileNotFoundError
    with pytest.raises(FileNotFoundError):
        cfg.load('.')

    # Loading a non-existent file path raises a FileNotFoundError
    with pytest.raises(FileNotFoundError):
        cfg.load('invalid_path.json')


def test_write_script_bat(resolver, tmpdir):
    cfg = resolver.resolve("not_set/child")
    file_config = tmpdir.join("config.bat")
    file_launch = tmpdir.join("launch.bat")
    # Batch is windows only, force the code to evaluate as if it was on windows
    cfg._platform_override = "windows"
    cfg.write_script(str(file_config), str(file_launch))

    config_text = file_config.open().read()
    launch_text = file_launch.open().read()

    # Ensure this test passes if run with cygwin or command prompt/powershell on windows
    alias = "C:\\Program Files\\Autodesk\\Maya2020\\bin"

    assert 'cmd.exe /k "{}"\n'.format(file_config) == launch_text

    assert 'set "PROMPT=[not_set/child] $P$G"' in config_text
    assert 'set "TEST=case"' in config_text
    # Expanded "{PATH:e}" and "{;}" formatting is applied correctly
    assert 'set "FMT_FOR_OS=a;b;c:%PATH%;d"' in config_text

    # Check that simple aliases are generated
    assert (
        r'C:\Windows\System32\doskey.exe maya="{}\maya.exe" $*'.format(alias)
        in config_text
    )
    # Check that list aliases are generated
    assert (
        r'C:\Windows\System32\doskey.exe pip="{}\mayapy.exe" -m pip $*'.format(alias)
        in config_text
    )


def test_write_script_ps1(resolver, tmpdir):
    cfg = resolver.resolve("not_set/child")
    file_config = tmpdir.join("config.ps1")
    file_launch = tmpdir.join("launch.ps1")
    # Powershell is windows only, force the code to evaluate as if it was on windows
    cfg._platform_override = "windows"
    cfg.write_script(str(file_config), str(file_launch))

    config_text = file_config.open().read()
    launch_text = file_launch.open().read()

    # Ensure this test passes if run with cygwin or command prompt/powershell on windows
    alias = "C:\\Program Files\\Autodesk\\Maya2020\\bin\\maya.exe"
    alias = cfg.shell_escape(".ps1", alias)

    assert (
        'powershell.exe -NoExit -ExecutionPolicy Unrestricted . "{}"\n'.format(
            file_config
        )
        == launch_text
    )
    assert "function PROMPT {'[not_set/child] ' + $(Get-Location) + '>'}" in config_text
    assert '$env:TEST = "case"' in config_text
    # Expanded "{PATH:e}" and "{;}" formatting is applied correctly
    assert '$env:FMT_FOR_OS = "a;b;c:$env:PATH;d"' in config_text

    # Check that simple aliases are generated
    assert r"function maya() {{ {} $args }}".format(alias) in config_text
    # Check that list aliases are generated
    alias = ntpath.join(ntpath.dirname(alias), "mayapy.exe")
    assert r"function pip() {{ {} -m pip $args }}".format(alias) in config_text


# Bash formatting is different on windows for env vars
@pytest.mark.parametrize(
    "platform,fmt_check", (("win32", "a;b;c:$PATH;d"), ("linux", "a:b;c:$PATH:d"))
)
def test_write_script_sh(resolver, tmpdir, monkeypatch, platform, fmt_check):
    # Bash formatting is different on windows for env vars
    monkeypatch.setattr(sys, 'platform', platform)

    cfg = resolver.resolve("not_set/child")
    file_config = tmpdir.join("config")
    file_launch = tmpdir.join("launch")
    cfg.write_script(str(file_config), str(file_launch))

    config_text = file_config.open().read()
    launch_text = file_launch.open().read()

    assert 'bash --init-file "{}"\n'.format(file_config) == launch_text
    assert 'export PS1="[not_set/child] $PS1"' in config_text
    assert 'export TEST="case"' in config_text
    # Expanded "{PATH:e}" and "{;}" formatting is applied correctly
    assert f'export FMT_FOR_OS="{fmt_check}"' in config_text

    # Check that simple aliases are generated
    assert r"function maya() {" in config_text
    assert r' "$@"; };export -f maya;' in config_text
    # Check that list aliases are generated
    assert r'function pip() { ' in config_text
    assert r' -m pip "$@"; };export -f pip;' in config_text


@pytest.mark.parametrize(
    "dirname,uri",
    (
        ("configs_parent", "not_set"),
        ("configs_child", "not_set/child"),
    ),
)
def test_duplicated_configs(config_root, resolver, dirname, uri):
    """Check that a specific config can be duplicated and that the first path
    is the used data. If there is a duplicate in the same config path, an exception
    is raised.

    The duplicates/*_1 folders have a second definition, but are in their own unique
    config_paths, so only the first found config is used.

    The duplicates/*_2 folders have a third definition. The second and third definitions
    are in the same config_path so a DuplicateJsonError is raised.
    """
    original = resolver.config_paths
    config_paths = list(original)
    # Check that config_paths raise exceptions correctly
    config_paths.insert(0, config_root / "duplicates" / f"{dirname}_1")
    resolver.config_paths = config_paths

    # Check that the first config in config_paths was used
    cfg = resolver.resolve(uri)
    assert f"{dirname}_1" in str(cfg.filename)

    # Check that an exception is raised if there are duplicate definitions from
    # the same config_paths directory.
    config_paths = list(original)
    config_paths.insert(0, config_root / "duplicates" / f"{dirname}_2")
    resolver.config_paths = config_paths
    with pytest.raises(DuplicateJsonError):
        resolver.resolve(uri)


def test_duplicated_distros(config_root, resolver):
    """Check that a specific config can be duplicated and that the first path
    is the used data. If there is a duplicate in the same config path, an exception
    is raised.

    The duplicates/distros_1 folders have a second definition, but are in their own
    unique config_paths, so only the first found config is used.

    The duplicates/distros_2 folders have a third definition. The second and third
    definitions are in the same config_path so a DuplicateJsonError is raised.
    """
    original = resolver.distro_paths

    # Check that the first config in distro_paths was used
    distro_paths = list(original)
    distro_paths.insert(0, config_root / "duplicates" / "distros_1" / "*")
    resolver.distro_paths = distro_paths

    dcc = resolver.find_distro("the_dcc==1.2")
    assert dcc.name == "the_dcc==1.2"
    assert "distros_1" in str(dcc.filename)

    # Check that an exception is raised if there are duplicate definitions from
    # the same distro_paths directory.
    distro_paths = list(original)
    distro_paths.insert(0, config_root / "duplicates" / "distros_2" / "*")
    resolver.distro_paths = distro_paths

    with pytest.raises(DuplicateJsonError):
        resolver.find_distro("the_dcc==1.2")
