import functools
import os
import re
import site
import subprocess
import sys

import pytest

from hab import Resolver, Site, utils
from hab.errors import HabError, InvalidAliasError


class Topen(subprocess.Popen):
    """A custom subclass of Popen."""


def missing_annotations_hack(function):
    """Decorator that works around a missing annotations module in python 3.6.

    Allows for calling subprocess calls in python 3.6 that would normally fail
    with a `SyntaxError: future feature annotations is not defined` exception.

    Works by temporarily removing the `_virtualenv.pth` file in the venv's
    site-packages.

    TODO: Figure out a better method until we can drop CentOS requirement.
    """

    @functools.wraps(function)
    def new_function(*args, **kwargs):
        if sys.version_info.minor != 6:
            return function(*args, **kwargs)

        site_packages = site.getsitepackages()
        for path in site_packages:
            pth = os.path.join(path, "_virtualenv.pth")
            if os.path.exists(pth):
                os.rename(pth, f"{pth}.bak")
        try:
            ret = function(*args, **kwargs)
        finally:
            for path in site_packages:
                pth = os.path.join(path, "_virtualenv.pth.bak")
                if os.path.exists(pth):
                    os.rename(pth, pth[:-3])
        return ret

    return new_function


def test_launch(resolver):
    """Check the Config.launch method."""
    cfg = resolver.resolve("app/aliased/mod")
    proc = cfg.launch("global", args=None, blocking=True)

    # Enabling mod_std sends all exception text to stdout
    assert proc.output_stderr is None
    check = [
        " Env Vars: ".center(80, "-"),
        "ALIASED_GLOBAL_A: ['Local Mod A', 'Local A Prepend', 'Global A', 'Local A Append']",
        "ALIASED_GLOBAL_B: ['Global B']",
        "ALIASED_GLOBAL_C: ['Local C Set']",
        "ALIASED_GLOBAL_D: <UNSET>",
        "ALIASED_GLOBAL_E: <UNSET>",
        "ALIASED_LOCAL: <UNSET>",
        "CONFIG_DEFINED: ['config_variable']",
        "",
        " PATH env var ".center(80, "-"),
    ]

    assert "\n".join(check) in proc.output_stdout


@missing_annotations_hack
def test_launch_str(resolver):
    cfg = resolver.resolve("app/aliased/mod")

    # Check that args are passed to the subprocess
    # Check that if "cmd" is a str, it is converted to a list and extended with args
    args = ["-c", 'print("success")']
    proc = cfg.launch("as_str", args=args, blocking=True)
    assert proc.output_stdout.strip() == "success"

    # Check that passing env is respected
    env = dict(os.environ)
    var_name = "TEST_ADDED_VARIABLE"
    var_value = "Test variable"
    assert var_name not in env
    env[var_name] = var_value

    # Check that Popen kwargs can be passed through launch, including env.
    args = [
        "-c",
        'import os;assert os.environ["{}"] != "{}"'.format(var_name, var_value),
    ]
    proc = cfg.launch("as_str", args=args, blocking=True, env=env)


@pytest.mark.skipif(sys.platform != "win32", reason="only applies on windows")
def test_pythonw(monkeypatch, resolver):
    """Check that sys.stdin is set if using pythonw."""
    cfg = resolver.resolve("app/aliased/mod")

    # If not using pythonw.exe proc.stdin is not routed to PIPE
    proc = cfg.launch("global", args=None, blocking=True)
    assert proc.stdin is None

    # If using pythonw.exe, proc.stdin is routed to PIPE
    pyw = re.sub("python.exe", "pythonw.exe", sys.executable, flags=re.I)
    monkeypatch.setattr(sys, "executable", pyw)
    proc = cfg.launch("global", args=None, blocking=True)
    assert proc.stdin is not None


def test_invalid_alias(resolver):
    cfg = resolver.resolve("app/aliased/mod")
    with pytest.raises(
        InvalidAliasError,
        match='The alias "not-a-alias" is not found for URI "app/aliased/mod".',
    ):
        cfg.launch("not-a-alias")

    # Remove the "cmd" value to test an invalid configuration
    alias = cfg.frozen_data["aliases"][utils.Platform.name()]["global"]
    del alias["cmd"]

    with pytest.raises(HabError, match='Alias "global" does not have "cmd" defined'):
        cfg.launch("global")


def test_cls_no_entry_point(resolver):
    """Check that if no entry point is defined, `hab.launcher.Launcher` is
    used to launch the alias.
    """
    entry_points = resolver.site.entry_points_for_group("hab.launch_cls")
    assert len(entry_points) == 0

    cfg = resolver.resolve("app/aliased/mod")
    proc = cfg.launch("global", blocking=True)

    from hab.launcher import Launcher

    assert type(proc) is Launcher

    # Check that specifying cls, overrides default
    proc = cfg.launch("global", blocking=True, cls=Topen)
    assert type(proc) is Topen


def test_cls_entry_point(config_root):
    """Check that if an entry point is defined, it is used unless overridden."""
    site = Site(
        [config_root / "site/site_entry_point_a.json", config_root / "site_main.json"]
    )
    entry_points = site.entry_points_for_group("hab.launch_cls")
    assert len(entry_points) == 1
    # Test that the `test-gui` `hab.cli` entry point is handled correctly
    ep = entry_points[0]
    assert ep.name == "subprocess"
    assert ep.group == "hab.launch_cls"
    assert ep.value == "subprocess:Popen"

    resolver = Resolver(site=site)
    cfg = resolver.resolve("app/aliased/mod")

    # Check that entry_point site config is respected
    proc = cfg.launch("global", blocking=True)
    assert type(proc) is subprocess.Popen

    # Check that specifying cls, overrides site config
    proc = cfg.launch("global", blocking=True, cls=Topen)
    assert type(proc) is Topen


def test_alias_entry_point(config_root):
    """Check that if an entry point is defined on a complex alias, it is used."""
    site = Site(
        [config_root / "site/site_entry_point_a.json", config_root / "site_main.json"]
    )

    resolver = Resolver(site=site)
    cfg = resolver.resolve("app/aliased/mod")

    # NOTE: We need to compare the name of the classes because they are separate
    # imports that don't compare equal using `is`.

    # Check that entry_point site config is respected
    proc = cfg.launch("global", blocking=True)
    assert type(proc).__name__ == "Popen"

    # Check that if the complex alias specifies hab.launch_cls, it is used instead
    # of the site defined or default class.
    alias = cfg.frozen_data["aliases"][utils.Platform.name()]["global"]
    alias["hab.launch_cls"] = {"subprocess": "tests.test_launch:Topen"}
    proc = cfg.launch("global", blocking=True)
    assert type(proc).__name__ == "Topen"


@pytest.mark.parametrize("exit_code", [5, 4, 0])
class TestCliExitCodes:
    """Test that calling `hab launch` runs python and passes a complex command string
    correctly. Also checks that exit-codes are properly returned to the caller.
    """

    # Note: Using as_str to call python. I ran into lockups when trying to call
    # a "python" alias defined in the hab tests.
    sub_cmd = ["launch", "app/aliased", "as_str", "-c"]
    # This complex string is passed to python, and ensures that complex strings
    # get encoded correctly for the generated shell scripts. It also proves that
    # we are getting text output from python. The sys.exit call is not required,
    # but is used to ensure that exit-codes are returned to the calling process.
    py_cmd = "print('Running...');import sys;print(sys);sys.exit({code})"
    output_text = "Running...\n<module 'sys' (built-in)>\n"
    run_kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5)
    if sys.version_info.minor >= 7:
        run_kwargs["text"] = True
    else:
        run_kwargs["universal_newlines"] = True

    @pytest.mark.skipif(sys.platform != "win32", reason="only applies on windows")
    @missing_annotations_hack
    def test_bat(self, config_root, exit_code):
        hab_bin = (config_root / ".." / "bin" / "hab.bat").resolve()
        # fmt: off
        cmd = [
            str(hab_bin), "--site", str(config_root / "site_main.json"),
            *self.sub_cmd,
            self.py_cmd.format(code=exit_code),
        ]
        # fmt: on

        # Run the hab command in a subprocess
        proc = subprocess.run(cmd, **self.run_kwargs)

        # Check that the print statement was actually run
        assert proc.stdout == self.output_text
        assert proc.returncode == exit_code

    @pytest.mark.skipif(sys.platform != "win32", reason="only applies on windows")
    @pytest.mark.skipif(
        os.getenv("GITHUB_ACTIONS") == "true",
        reason="PowerShell tests timeout when run in a github action",
    )
    @missing_annotations_hack
    def test_ps1(self, config_root, exit_code):
        # -File is needed to get the exit-code from powershell, and requires a full path
        script = (config_root / ".." / "bin" / "hab.ps1").resolve()
        # fmt: off
        cmd = [
            "powershell.exe", "-ExecutionPolicy", "Unrestricted",
            "-File", str(script),
            "--site", str(config_root / "site_main.json"),
            *self.sub_cmd,
            f"\"{self.py_cmd.format(code=exit_code)}\"",
        ]
        # fmt: on

        # Run the hab command in a subprocess
        proc = subprocess.run(cmd, **self.run_kwargs)

        # Check that the print statement was actually run
        assert proc.stdout == self.output_text
        assert proc.returncode == exit_code

    @pytest.mark.skip(reason="Find a way to make this test run successfully")
    def test_bash_win(self, config_root, exit_code):
        # fmt: off
        cmd = [
            "hab",
            "--site", f'{(config_root / "site_main.json").as_posix()}',
            *self.sub_cmd,
            self.py_cmd.format(code=exit_code),
        ]
        cmd = [
            # Note: This requires compatible with git bash, or the `--site` path
            # gets mangled.
            os.path.expandvars(r"%PROGRAMFILES%\Git\usr\bin\bash.exe"),
            "--login", "-c", subprocess.list2cmdline(cmd)
        ]
        # fmt: on

        # Run the hab command in a subprocess
        print(
            "# If you run this command in a command prompt the expected results "
            "are printed, but calling it here doesn't return any results."
        )
        print('# Make sure to check the exit-code with "echo %ERRORLEVEL%"')
        print(subprocess.list2cmdline(cmd))
        proc = subprocess.run(cmd, **self.run_kwargs)
        print(proc.stdout)
        print(proc.stderr)

        # Check that the print statement was actually run
        assert proc.stdout == self.output_text
        assert proc.returncode == exit_code

    @pytest.mark.skip(reason="Find a way to make this test run successfully")
    def test_bash_linux(self, config_root, exit_code):
        hab_bin = (config_root / ".." / "bin" / "hab").resolve()

        # fmt: off
        cmd = [
            hab_bin,
            "--site", f'{(config_root / "site_main.json")}',
            *self.sub_cmd,
            self.py_cmd.format(code=exit_code),
        ]
        # fmt: on

        # Run the hab command in a subprocess
        print(
            "# Run this command in a bash shell and verify that the expected results"
            " are printed. TODO: figure out how to run this with pytest."
        )
        print('# Make sure to check the exit-code with "echo $?"')
        print(subprocess.list2cmdline(cmd))
        proc = subprocess.run(cmd, shell=True, **self.run_kwargs)
        print(proc.stdout)
        print(proc.stderr)

        # Check that the print statement was actually run
        assert proc.stdout == self.output_text
        assert proc.returncode == exit_code
