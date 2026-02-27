import os
import re
import subprocess
import sys

import pytest

from hab import Resolver, Site, utils
from hab.errors import HabError, InvalidAliasError


class Topen(subprocess.Popen):
    """A custom subclass of Popen."""


def test_launch(habcached_resolver):
    """Check the Config.launch method."""
    cfg = habcached_resolver.resolve("app/aliased/mod")
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


def test_launch_str(habcached_resolver):
    cfg = habcached_resolver.resolve("app/aliased/mod")

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
        f'import os;assert os.environ["{var_name}"] != "{var_value}"',
    ]
    proc = cfg.launch("as_str", args=args, blocking=True, env=env)


@pytest.mark.skipif(sys.platform != "win32", reason="only applies on windows")
def test_pythonw(monkeypatch, habcached_resolver):
    """Check that sys.stdin is set if using pythonw."""
    cfg = habcached_resolver.resolve("app/aliased/mod")

    # If not using pythonw.exe proc.stdin is not routed to PIPE
    proc = cfg.launch("global", args=None, blocking=True)
    assert proc.stdin is None

    # If using pythonw.exe, proc.stdin is routed to PIPE
    pyw = re.sub("python.exe", "pythonw.exe", sys.executable, flags=re.I)
    monkeypatch.setattr(sys, "executable", pyw)
    proc = cfg.launch("global", args=None, blocking=True)
    assert proc.stdin is not None


def test_invalid_alias(habcached_resolver):
    cfg = habcached_resolver.resolve("app/aliased/mod")
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


def test_cls_no_entry_point(habcached_resolver):
    """Check that if no entry point is defined, `hab.launcher.Launcher` is
    used to launch the alias.
    """
    entry_points = habcached_resolver.site.entry_points_for_group("hab.launch_cls")
    assert len(entry_points) == 0

    cfg = habcached_resolver.resolve("app/aliased/mod")
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
    run_kwargs = dict(
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5, text=True
    )

    @pytest.mark.parametrize("shell", ("bat", "ps1", "bash_win", "bash_linux"))
    def test_exit_code(self, shell, exit_code, config_root, tmp_path, run_hab):
        # Skip tests that will not run on the current platform
        run_hab.skip_wrong_platform(shell)

        # Run the hab command in a subprocess
        sub_cmd = [
            *self.sub_cmd,
            *[self.py_cmd.format(code=exit_code)],
        ]
        runner = run_hab(config_root, tmp_path)
        proc = runner.run_in_shell(shell, sub_cmd)

        with runner.std_on_failure(proc):
            # Check that the print statement was actually run
            assert proc.stdout == self.output_text
            assert proc.returncode == exit_code
