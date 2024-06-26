import json
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

from hab import errors, utils

# Create a test for each dir in reference_scripts. We pass the name of the folder
# so test selection matches the name of the folder instead of something abstract
# like [reference5].
reference_scripts = Path(__file__).parent / "reference_scripts"
reference_names = [x.name for x in reference_scripts.iterdir()]


@pytest.mark.parametrize("reference_name", reference_names)
def test_scripts(uncached_resolver, tmpdir, monkeypatch, config_root, reference_name):
    """Checks all of the scripts HabBase.write_script generates for a specified
    set of arguments.

    This is a parametrized test, and each folder inside the tests/reference_scripts
    directory adds a test. Each directory needs a spec.json file similar to this::

        {
            "description": "[shell and platform]: Tests `hab [command] [uri]`",
            "ext": ".sh",
            "launch": null,
            "exiting": false,
            "args": null,
            "create_launch": false,
            "platform": "linux",
            "uri": "not_set/child"
        }

    A reference directory needs to have at least one script file generated by hab,
    and all files are expected to be created by write_script.

    To add a new test, create the new directory and add the desired spec file.
    Run the test(it will fail) and in the pytest temp directory you can find the
    script files that hab generated for your spec. Copy them into your reference
    directory. You will then need to replace the hard coded file paths with jinja2
    templates to ensure your test will pass on the next run of pytest, as well
    as when the git checkout is in a different location. There are a few required
    replacements needed:

    1. Replace the path to the test's tempdir with `{{ tmpdir }}`. If joining
        paths to tmpdir, do it as part of the format to ensure correct slash
        direction. `{{ tmpdir / "filename.txt" }}`
    2. Replace the path to your checkout's tests directory with `{{ config_root }}`
        making sure to convert back slashes to forward slashes
    3. Replace the HAB_FREEZE value with `{{ freeze }}`.
    """
    reference = reference_scripts / reference_name
    spec = json.load((reference / "spec.json").open())

    if "description" in spec:
        print(f"Testing: {spec['description']}")

    # Script formatting is subtly different on different platforms, ensure we
    # are testing the requested platform, not the current one.
    platform = spec["platform"]
    assert platform in ("linux", "osx", "win32")
    monkeypatch.setattr(utils, "Platform", utils.BasePlatform.get_platform(platform))

    cfg = uncached_resolver.resolve(spec["uri"])
    reference = config_root / "reference_scripts" / reference_name
    ext = spec["ext"]

    cfg.write_script(
        str(tmpdir),
        ext=ext,
        launch=spec["launch"],
        exit=spec["exiting"],
        args=spec["args"],
        create_launch=spec["create_launch"],
    )

    # Generate the correct testing path for the shell this test is targeting
    func = utils.path_forward_slash
    if platform == "win32" and ext == ".sh":
        func = utils.cygpath

    # Test specific values to update the reference templates with for comparison
    replacements = {
        "freeze": utils.encode_freeze(cfg.freeze()),
        # Replace the path to the test's tempdir with `{{ tmpdir }}`
        "tmpdir": tmpdir,
        # Replace the path to your checkout's tests directory with
        # `{{ config_root }}` making sure to convert back slashes to forward slashes
        "config_root": func(config_root),
        # For bash on windows, we are not converting "cmd" to cygpaths as it's
        # not required and we would then need to account for multiple paths in
        # the same string.
        "config_root_alias": utils.path_forward_slash(config_root),
    }

    def check_file(item):
        rel_path = item.relative_to(reference)
        generated = tmpdir / rel_path

        # Fill in the dynamic variables in the reference file to ensure the test
        # passes for the current git checkout location and pytest's temp dir.
        # Using Jinja for this because other python str formatting methods require
        # too much manipulation of the reference files.
        environment = Environment(
            loader=FileSystemLoader(str(item.parent)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        template = environment.get_template(item.name)
        # Note: jinja2' seems to be inconsistent with its trailing newlines depending
        # on the template and its if statements, so force a single trailing newline
        ref_text = template.render(**replacements).rstrip() + "\n"

        try:
            assert generated.exists()
            assert (
                ref_text == generated.open().read()
            ), "Reference does not match generated"
        except AssertionError:
            print("")
            print(f"Reference: {item}")
            print(f"Generated: {generated}")
            raise

    reference_paths = []

    def walk_dir(current):
        found_script = False
        for item in current.iterdir():
            if item.name == "spec.json":
                continue
            elif item.is_file():
                check_file(item)
                # At least one file was found beyond spec.json so test is valid
                found_script = True
            else:
                walk_dir(item)
            # Include the directory name so we match the rglob results below
            reference_paths.append(item)
        assert (
            found_script
        ), f"Reference dir needs to contain at least one script. {reference}"

    walk_dir(reference)

    # Check that we created the same number of files as the template
    processed_paths = sorted(Path(tmpdir).rglob("*"))
    reference_paths = sorted(reference_paths)

    total_processed = len(processed_paths)
    total_reference = len(reference_paths)
    assert (
        total_reference == total_processed
    ), "Reference file count doesn't match generated"

    # File paths should only be converted to the scripting language(cygpath)
    # only when generating a script, not before that. Check that the path was
    # not converted while building frozen data.
    # This check exists to ensure that we don't accidentally break this
    # requirement at some point in the future.
    freeze = cfg.freeze()
    for plat in ("linux", "windows"):
        alias = freeze["aliases"][plat]["inherited"]
        env = alias["environment"]["PATH"]
        distro = config_root / "distros" / "aliased" / "2.0"

        assert Path(alias["cmd"][1]) == distro / "list_vars.py"

        assert env[0] == "{PATH!e}"
        assert Path(env[1]) == distro / "PATH" / "env" / "with  spaces"


@pytest.mark.skip(reason="Find a way to test complex alias evaluation in pytest")
def test_complex_alias_bat(tmpdir, config_root):
    """This test is a placeholder for a future that can actually call hab's `hab.cli`
    and its aliases to check that they function correctly in Batch.

    This example text shows that using "hab env" can set an environment variable,
    and a complex alias call can modify that env var for the called command, but
    when the alias exits, the original env var is returned.
    """
    hab_paths = config_root / "site_main.json"
    test = (
        "REM Use the correct hab site configuration",
        f'set "HAB_PATHS={hab_paths}"',
        "REM activate the current hab environment",
        "hab env app/aliased/mod",
        'REM At this point the env var is set to "Global A"',
        'echo "In Hab env: " %ALIASED_GLOBAL_A%',
        "REM Call the alias, and check its output against the next section.",
        "REM This is showing that the alias process has modified env vars.",
        "global test",
        "REM After the alias was run, the global env var is restored",
        'echo "after calling function: " %ALIASED_GLOBAL_A%',
    )

    print("## Run these commands one at a time in a new bash terminal:")
    print("")
    print("\n".join(test))
    print("")
    print("## The output of calling global, should include:")
    print("- The `sys.argv:` line should include the test string passed to global")
    print(
        "- ALIASED_GLOBAL_A: ['Local Mod A', 'Local A Prepend', 'Global A', "
        "'Local A Append']"
    )
    raise AssertionError("Run this test manually line by line in a Command Prompt")


@pytest.mark.skip(reason="Find a way to test complex alias evaluation in pytest")
def test_complex_alias_ps1(tmpdir, config_root):
    """This test is a placeholder for a future that can actually call hab's `hab.cli`
    and its aliases to check that they function correctly in PowerShell.

    This example text shows that using "hab env" can set an environment variable,
    and a complex alias call can modify that env var for the called command, but
    when the alias exits, the original env var is returned.
    """
    hab_paths = config_root / "site_main.json"
    test = (
        "# Use the correct hab site configuration",
        f'$env:HAB_PATHS="{hab_paths}"',
        "# activate the current hab environment",
        "hab env app/aliased/mod",
        '# At this point the env var is set to "Global A"',
        'echo "In Hab env: " $env:ALIASED_GLOBAL_A',
        "# Call the alias, and check its output against the next section.",
        "# This is showing that the alias process has modified env vars.",
        "global test",
        "# After the alias was run, the global env var is restored",
        'echo "after calling function: " $env:ALIASED_GLOBAL_A',
    )

    print("## Run these commands one at a time in a new bash terminal:")
    print("")
    print("\n".join(test))
    print("")
    print("## The output of calling global, should include:")
    print("- The `sys.argv:` line should include the test string passed to global")
    print(
        "- ALIASED_GLOBAL_A: ['Local Mod A', 'Local A Prepend', 'Global A', "
        "'Local A Append']"
    )
    raise AssertionError("Run this test manually line by line in a PowerShell")


@pytest.mark.skip(reason="Find a way to test complex alias evaluation in pytest")
def test_complex_alias_sh(tmpdir, config_root):
    """This test is a placeholder for a future that can actually call hab's `hab.cli`
    and its aliases to check that they function correctly in Bash.

    This example text shows that using "hab env" can set an environment variable,
    and a complex alias call can modify that env var for the called command, but
    when the alias exits, the original env var is returned.
    """
    hab_paths = config_root / "site_main.json"
    test = (
        "# Use the correct hab site configuration",
        f'export HAB_PATHS="{hab_paths}"',
        "# activate the current hab environment",
        "hab env app/aliased/mod",
        '# At this point the env var is set to "Global A"',
        'echo "In Hab env: " $ALIASED_GLOBAL_A',
        "# Call the alias, and check its output against the next section.",
        "# This is showing that the alias process has modified env vars.",
        "global test",
        "# After the alias was run, the global env var is restored",
        'echo "after calling function: " $ALIASED_GLOBAL_A',
    )

    print("## Run these commands one at a time in a new bash terminal:")
    print("")
    print("\n".join(test))
    print("")
    print("## The output of calling global, should include:")
    print("- The `sys.argv:` line should include the test string passed to global")
    print(
        "- ALIASED_GLOBAL_A: ['Local Mod A', 'Local A Prepend', 'Global A', "
        "'Local A Append']"
    )
    raise AssertionError("Run this test manually line by line in a bash shell")


@pytest.mark.parametrize("ext", (".bat", ".ps1", ".sh"))
def test_invalid_alias(uncached_resolver, tmpdir, ext):
    """Check that useful errors are raised if an invalid alias is passed or if
    the alias doesn't have "cmd" defined.
    """
    kwargs = dict(ext=ext, exit=True, args=None, create_launch=True)

    # Check that calling a bad alias name raises a useful error message
    cfg = uncached_resolver.resolve("not_set/child")
    with pytest.raises(
        errors.InvalidAliasError,
        match=r'The alias "bad-alias" is not found for URI "not_set/child".',
    ):
        cfg.write_script(str(tmpdir), launch="bad-alias", **kwargs)

    # Remove the "cmd" value to test an invalid configuration
    alias = cfg.frozen_data["aliases"][utils.Platform.name()]["global"]
    del alias["cmd"]

    with pytest.raises(
        errors.HabError, match='Alias "global" does not have "cmd" defined'
    ):
        cfg.write_script(str(tmpdir), launch="global", **kwargs)
