from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from hab import utils
from hab.formatter import Formatter


@dataclass
class FileRef:
    path: Path
    name: str = field(init=False)
    shell: str | None = field(default=None)
    platform: str = field(init=False)
    distros: list = field(init=False)
    alias: str = field(init=False)
    _parser = re.compile(
        r"(?P<platform>[^-]+)-(?P<distros>[^-]+)-(?P<alias>[^.]+).json"
    )

    def __post_init__(self) -> None:
        if not hasattr(self, "name"):
            self.name = self.path.stem
            match = self._parser.match(self.path.name)
            if not match:
                raise ValueError(f"Invalid filename: {self.path}")
            kwargs = match.groupdict()
            self.platform = kwargs["platform"]
            self.distros = kwargs["distros"].split(",")
            self.alias = kwargs["alias"]

    @classmethod
    def from_glob(cls, path, glob_str="*.json"):
        ret = []
        for filename in utils.natural_sort(path.glob(glob_str)):
            ret.append(cls(filename))
        return ret

    @classmethod
    def shell_matrix(cls, file_refs, shells: dict[str, list]) -> list:
        ret = []
        for file_ref in file_refs:
            plat_shells = shells.get(file_ref.platform, [])
            for shell in plat_shells:
                ref = copy.copy(file_ref)
                ref.shell = shell
                ret.append(ref)
        ret.sort(key=lambda i: repr(i))
        return ret

    def __repr__(self) -> str:
        if self.shell:
            return f"{self.shell},{self.name}"
        return self.name


references = FileRef.from_glob(Path(__file__).parent / "var_expanding")
shell_references = FileRef.shell_matrix(
    references, {"windows": ["bash_win", "bat", "ps1"], "linux": ["bash_linux"]}
)


@pytest.mark.parametrize("reference", shell_references, ids=lambda f: repr(f))
def test_shell_expanding(reference, config_root, tmp_path, run_hab):
    # Skip tests that will not run on the current platform
    run_hab.skip_wrong_platform(reference.shell)

    runner = run_hab(config_root, tmp_path, stderr=subprocess.PIPE)
    sub_cmd = []
    for d in reference.distros:
        sub_cmd.extend(["-r", f"var-expand-{d}"])
    sub_cmd += ["launch", "", reference.alias]
    proc = runner.run_in_shell(reference.shell, sub_cmd)

    with runner.std_on_failure(proc):
        # Check that the env vars were set as expected
        assert proc.returncode == 0

        # Replace `{;;}` with the correct pathsep for the test. This is required because
        # bash on windows uses the linux pathsep
        languages = {
            "bat": "batch",
            "ps1": "ps",
            "bash_win": "shwin",
            "bash_linux": "sh",
        }
        pathsep = Formatter.shell_formats[languages[reference.shell]][";"]
        check = reference.path.open().read()
        check = check.replace("{;;}", pathsep)

        assert proc.stdout == check


@pytest.mark.parametrize("reference", references, ids=lambda f: repr(f))
def test_subprocess_launch(habcached_resolver, reference):
    pathsep = ":"
    if sys.platform.startswith("linux"):
        if reference.platform != "linux":
            raise pytest.skip("test doesn't apply on linux")
    elif sys.platform == "win32":
        pathsep = ";"
        if reference.platform != "windows":
            raise pytest.skip("test doesn't apply on windows")

    forced_requirements = []
    for d in reference.distros:
        forced_requirements.extend([f"var-expand-{d}"])
    cfg = habcached_resolver.resolve("", forced_requirements=forced_requirements)

    proc = cfg.launch(reference.alias, args=None, blocking=True, stderr=subprocess.PIPE)
    assert proc.returncode == 0

    # Replace `{;;}` with the correct pathsep for the test. This is required because
    # bash on windows uses the linux pathsep
    check = reference.path.open().read()
    check = check.replace("{;;}", pathsep)

    assert proc.output_stdout == check


@pytest.mark.parametrize("alias", ("list_vars", "list_vars_env"))
class TestShellResolutionOrder:
    """Verify that we get the same env var settings for shell and subprocess launches."""

    def check(self, alias):
        """Returns the expected output from running the given alias."""
        on_linux = sys.platform.startswith("linux")
        on_win = sys.platform == "win32"

        def unset(plat, value):
            """Returns "<UNSET>" if the current platform is not plat."""
            if plat:
                return value
            return "<UNSET>"

        def for_plat(fmt):
            return fmt.format("linux" if on_linux else "windows")

        if alias == "list_vars":
            return json.dumps(
                {
                    "EXPAND_WILD_PRE": "-*--",
                    "EXPAND_C": for_plat("expand-c-{}"),
                    "EXPAND_WILD_POST": "-*-expand-c-wild-",
                    "EXPAND_LINUX_PRE": unset(on_linux, "-L-expand-c-linux-"),
                    "EXPAND_LINUX_POST": unset(on_linux, "-L-expand-c-linux-"),
                    "EXPAND_WINDOWS_PRE": unset(on_win, "-W-expand-c-windows-"),
                    "EXPAND_WINDOWS_POST": unset(on_win, "-W-expand-c-windows-"),
                    "MERGE_C": for_plat("WILD,{}"),
                    "EXPAND_ALIAS_PRE": "<UNSET>",
                    "EXPAND_ALIAS_POST": "<UNSET>",
                    "PY_EXPAND_WILD": "-not-e-*-WILD-",
                    "PY_EXPAND_LINUX": unset(on_linux, "-not-e-L-WILD,linux-"),
                    "PY_EXPAND_WINDOWS": unset(on_win, "-not-e-W-WILD,windows-"),
                },
                indent=4,
            )

        elif alias == "list_vars_env":
            return json.dumps(
                {
                    "EXPAND_WILD_PRE": "-*--",
                    "EXPAND_C": "expand-c-alias",
                    "EXPAND_WILD_POST": "-*-expand-c-wild-",
                    "EXPAND_LINUX_PRE": unset(on_linux, "-L-expand-c-linux-"),
                    "EXPAND_LINUX_POST": unset(on_linux, "-L-expand-c-linux-"),
                    "EXPAND_WINDOWS_PRE": unset(on_win, "-W-expand-c-windows-"),
                    "EXPAND_WINDOWS_POST": unset(on_win, "-W-expand-c-windows-"),
                    "MERGE_C": for_plat("WILD,{},ALIAS"),
                    "EXPAND_ALIAS_PRE": "-*-expand-c-alias-",
                    "EXPAND_ALIAS_POST": "-*-expand-c-alias-",
                    "PY_EXPAND_WILD": "-not-e-*-WILD-",
                    "PY_EXPAND_LINUX": unset(on_linux, "-not-e-L-WILD,linux-"),
                    "PY_EXPAND_WINDOWS": unset(on_win, "-not-e-W-WILD,windows-"),
                },
                indent=4,
            )

    @pytest.mark.parametrize("shell", ("bat", "ps1", "bash_win", "bash_linux"))
    def test_shell(self, shell, alias, config_root, tmp_path, run_hab):
        # Skip tests that will not run on the current platform
        run_hab.skip_wrong_platform(shell)

        runner = run_hab(config_root, tmp_path, stderr=subprocess.PIPE)
        # fmt: off
        sub_cmd = [
            "-r", "var-expand-c",
            "launch", "", alias
        ]
        # fmt: on
        proc = runner.run_in_shell(shell, sub_cmd)

        with runner.std_on_failure(proc):
            # Check that the env vars were set as expected
            assert proc.returncode == 0
            assert proc.stdout.rstrip() == self.check(alias)

    def test_subprocess(self, alias, habcached_resolver):
        # pathsep = ";" if sys.platform == "win32" else ":"
        forced_requirements = ["var-expand-c"]
        cfg = habcached_resolver.resolve("", forced_requirements=forced_requirements)

        proc = cfg.launch(alias, args=None, blocking=True, stderr=subprocess.PIPE)
        assert proc.returncode == 0

        assert proc.output_stdout.rstrip() == self.check(alias)
