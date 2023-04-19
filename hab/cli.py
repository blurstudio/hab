import logging
import re
import sys
import traceback
from pathlib import Path

import click
from colorama import Fore

from . import Resolver, Site, __version__
from .parsers.unfrozen_config import UnfrozenConfig
from .utils import decode_freeze, dumps_json, encode_freeze, json

logger = logging.getLogger(__name__)


# No one wants to actually type `--help`
CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


class UnfrozenType(click.Path):
    """Accepts a hab frozen string, or a file path to a document containing a
    frozen hab configuration. Returns the decoded python dictionary.
    """

    name = "unfrozen"

    def __init__(
        self, exists=True, path_type=Path, file_okay=True, resolve_path=True, **kwargs
    ):
        super().__init__(
            exists=exists,
            path_type=path_type,
            file_okay=file_okay,
            resolve_path=resolve_path,
            **kwargs,
        )

    def convert(self, value, param, ctx):
        if re.match(r'^v\d+:', value):
            return decode_freeze(value)

        # If its not a string, convert to a Path object matching requirements
        try:
            data = super().convert(value, param, ctx)
        except ValueError:
            self.fail(
                f"{value!r} is not a valid frozen version or file path.", param, ctx
            )
        return json.load(data.open())


class SharedSettings(object):
    def __init__(
        self,
        site_paths=None,
        verbosity=0,
        script_dir=None,
        script_ext=None,
        pre=None,
        forced_requirements=None,
        dump_scripts=False,
    ):
        self.verbosity = verbosity
        self.script_dir = Path(script_dir or ".").resolve()
        self.script_ext = script_ext
        self._resolver = None
        self.prereleases = pre
        self.forced_requirements = forced_requirements
        self.dump_scripts = dump_scripts
        self.site = Site([Path(p) for p in site_paths])

    @property
    def resolver(self):
        if self._resolver is None:
            self._resolver = Resolver(
                site=self.site,
                prereleases=self.prereleases,
                forced_requirements=self.forced_requirements,
            )
            self._resolver.dump_scripts = self.dump_scripts
        return self._resolver

    def write_script(
        self,
        uri,
        unfreeze=None,
        launch=None,
        exit=False,
        args=None,
        create_launch=False,
    ):
        """Generate the script the calling shell scripts expect to setup the environment"""
        logger.info(f"Context: {uri}")
        logger.debug(f"Script dir: {self.script_dir} ext: {self.script_ext}")

        if args:
            # convert to list, subprocess.list2cmdline does not like tuples
            args = list(args)

        if unfreeze:
            # Load frozen json data instead of processing the URI
            ret = UnfrozenConfig(unfreeze, self.resolver)
        elif uri is None:
            # If the user didn't choose a different report type, or use the
            # unfreeze option, raise the exception click would raise if
            # uri didn't have `required=False`.
            raise click.UsageError("Missing argument 'URI'.")
        else:
            # Otherwise just process the uri like normal
            ret = self.resolver.resolve(uri)

        ret.write_script(
            self.script_dir,
            self.script_ext,
            launch=launch,
            exit=exit,
            args=args,
            create_launch=create_launch,
        )


# This variable is used to keep track of the user enabled verbose hab output
# using `hab -v ...`. If they do, the full traceback is printed to the shell,
# otherwise just the last part of the traceback is printed so its easier to
# report and hopefully more descriptive.
_verbose_errors = False


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(__version__, prog_name="hab")
@click.option(
    "--site",
    "site_paths",
    multiple=True,
    type=click.Path(file_okay=True, resolve_path=True),
    help="One or more site json files to load settings from. Uses the env var "
    "`HAB_PATHS` if not passed. The values in each file are merged into a single "
    "dict with the right most value of any given configuration option being used.",
)
@click.option(
    "-v",
    "--verbose",
    "verbosity",
    count=True,
    help="Increase the verbosity of the output. Can be used up to 3 times. "
    "This also enables showing a full traceback if an exception is raised.",
)
@click.option(
    "--script-dir",
    type=click.Path(file_okay=False, resolve_path=False),
    help="This directory will contain the shell specific script files to enable"
    "this environment configuration.",
)
@click.option(
    "--script-ext",
    help="The shell specific scripts created in script-dir will have this "
    "format and extension.",
)
@click.option(
    "--pre/--no-pre",
    default=None,
    help="Include pre-releases when finding the latest distro version.",
)
@click.option(
    "-r",
    "--requirement",
    multiple=True,
    help="Forces this distro requirement ignoring normally resolved requirements. Using "
    "this may lead to configuring your environment incorrectly, use with caution.",
)
@click.option(
    "--dump-scripts/--no-dump-scripts",
    default=False,
    help=(
        "Print the generated scripts hab uses for this command instead of "
        "running them. This does not work for dump."
    ),
)
@click.pass_context
def _cli(
    ctx, site_paths, verbosity, script_dir, script_ext, pre, requirement, dump_scripts
):
    global _verbose_errors

    ctx.obj = SharedSettings(
        site_paths, verbosity, script_dir, script_ext, pre, requirement, dump_scripts
    )
    if verbosity > 2:
        verbosity = 2
    _verbose_errors = bool(verbosity)

    level = [logging.WARNING, logging.INFO, logging.DEBUG][verbosity]
    logging.basicConfig(level=level)


@_cli.command()
@click.argument("uri", required=False)
@click.option(
    "-u",
    "--unfreeze",
    type=UnfrozenType(),
    help="Path to frozen json file to load instead of specifying a URI.",
)
@click.option(
    "-l",
    "--launch",
    default=None,
    help="Run this alias after activating. This leaves the new shell active.",
)
@click.pass_obj
def env(settings, uri, unfreeze, launch):
    """Configures and launches a new shell with the resolved setup."""

    settings.write_script(uri, unfreeze=unfreeze, create_launch=True, launch=launch)


@_cli.command()
# If the report_type and unfreeze options are used, uri is not required. This
# is manually checked in the code below where it raises `click.UsageError`.
@click.argument("uri", required=False)
@click.pass_obj
@click.option(
    "--env/--no-env",
    default=True,
    help="Show the environment variable as a flattened structure.",
)
@click.option(
    "--env-config/--no-env-config",
    "--envc/--no-envc",
    default=False,
    help="Show the environment variable as a flattened structure.",
)
@click.option(
    "-t",
    "--type",
    "report_type",
    type=click.Choice(
        ["nice", "site", "s", "uris", "u", "versions", "v", "forest", "f"]
    ),
    default="nice",
    help="Type of report.",
)
@click.option(
    "--flat/--no-flat",
    default=True,
    help="Flatten the resolved object",
)
@click.option(
    "-v",
    "--verbose",
    "verbosity",
    count=True,
    help="Show increasingly detailed output. Can be used up to 3 times.",
)
@click.option(
    "-u",
    "--unfreeze",
    type=UnfrozenType(),
    help="Path to frozen json file to load instead of specifying a URI.",
)
@click.option(
    "-f",
    "--format",
    "format_type",
    type=click.Choice(["nice", "freeze", "json", "versions"]),
    default="nice",
    help="Choose how the output is formatted.",
)
def dump(
    settings, uri, env, env_config, report_type, flat, verbosity, unfreeze, format_type
):
    """Resolves and prints the requested setup."""
    logger.info("Context: {}".format(uri))
    # Convert report_tupe short names to long names for ease of processing
    report_map = {"u": "uris", "v": "versions", "f": "forest", "s": "site"}
    report_type = report_map.get(report_type, report_type)

    if report_type in ("uris", "versions", "forest"):
        # Allow the user to disable truncation of versions with verbosity flag
        truncate = None if verbosity else 3

        def echo_line(line):
            if line.strip() == line:
                click.echo(f'{Fore.GREEN}{line}{Fore.RESET}')
            else:
                click.echo(line)

        if report_type in ("uris", "forest"):
            click.echo(f'{Fore.YELLOW}{" URIs ".center(50, "-")}{Fore.RESET}')
            for line in settings.resolver.dump_forest(settings.resolver.configs):
                echo_line(line)
        if report_type in ("versions", "forest"):
            click.echo(f'{Fore.YELLOW}{" Versions ".center(50, "-")}{Fore.RESET}')
            for line in settings.resolver.dump_forest(
                settings.resolver.distros,
                attr="name",
                truncate=truncate,
            ):
                echo_line(line)
    elif report_type == "site":
        click.echo(settings.resolver.site.dump(verbosity=verbosity))
    else:
        if unfreeze:
            ret = UnfrozenConfig(unfreeze, settings.resolver)
        elif uri is None:
            # If the user didn't choose a different report type, or use the
            # unfreeze option, raise the exception click would raise if
            # uri didn't have `required=False`.
            raise click.UsageError("Missing argument 'URI'.")
        elif flat:
            ret = settings.resolver.resolve(uri)
        else:
            ret = settings.resolver.closest_config(uri)

        if format_type == "freeze":
            ret = encode_freeze(
                ret.freeze(), version=settings.resolver.site.get("freeze_version")
            )
        elif format_type == "json":
            ret = dumps_json(ret.freeze(), indent=2)
        elif format_type == "versions":
            ret = '\n'.join([v.name for v in ret.versions])
        else:
            ret = ret.dump(
                environment=env, environment_config=env_config, verbosity=verbosity
            )

        click.echo(ret)


@_cli.command()
@click.argument("uri", required=False)
@click.option(
    "-u",
    "--unfreeze",
    type=UnfrozenType(),
    help="Path to frozen json file to load instead of specifying a URI.",
)
@click.option(
    "-l",
    "--launch",
    default=None,
    help="Run this alias after activating. This leaves the new shell activated.",
)
@click.pass_obj
def activate(settings, uri, unfreeze, launch):
    """Resolves the setup and updates in the current shell.

    In powershell and bash you must use the source dot: ". hab activate ..."
    WARNING: Not supported in Command Prompt currently.
    """
    if settings.script_ext in (".bat", ".cmd"):
        # The hab shell scripts clean up their temp script files before exiting.
        # Due to batch not having a `function` feature we have to create the
        # aliases as extra script files to support complex aliases. We can't use
        # doskey if we want to support complex aliases. Another reason to avoid
        # doskey, is that it leaks assignments to the parent command prompt when
        # using it for env/launch so exiting doesn't get rid of aliases in those
        # modes. The env/launch commands continue to run till the user exits, but
        # activate exits immediately so the temp alias batch files get deleted
        # before they can be used by the user/script breaking this command.
        click.echo(
            f"{Fore.RED}Not Supported:{Fore.RESET} Using hab activate in the "
            "Command Prompt is not currently supported."
        )
        sys.exit(1)

    settings.write_script(uri, unfreeze=unfreeze, launch=launch)


@_cli.command(
    context_settings=dict(
        ignore_unknown_options=True,
    )
)
@click.argument("uri", required=False)
@click.option(
    "-u",
    "--unfreeze",
    type=UnfrozenType(),
    help="Path to frozen json file to load instead of specifying a URI.",
)
@click.argument("alias", required=False)
# Pass all remaining arguments to the requested alias
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
@click.pass_obj
def launch(settings, uri, unfreeze, alias, args):
    """Configure and launch an alias without modifying the current shell.
    The first argument is a URI, The second argument is the ALIAS to launch. Any
    additional arguments are passed as launch arguments to the alias. Note, if using
    bash on windows you may need to pass file paths correctly for bash as any quotes
    used may not make it to the alias launch arguments.
    (ie: '/c/Program\\ Files').
    """
    # To support making URI not required if unfreeze is specified, we have to
    # do all of the validation click would normally do ourselves.
    if unfreeze:
        # If using --unfreeze, uri contains the alias, and alias contains
        # the first argument if provided, and args contains any remaining
        # arguments. Rebuild them so they are the correct values.
        if alias is not None:
            args = (alias,) + args
        alias = uri
        uri = None
    elif not uri:
        # Provide user feedback if a neither uri or unfreeze are provided
        raise click.UsageError("Missing argument 'URI'.")

    if not alias:
        # If alias was not provided, replicate the error click normally raises
        raise click.UsageError("Missing argument 'ALIAS'.")

    settings.write_script(
        uri, unfreeze=unfreeze, create_launch=True, launch=alias, exit=True, args=args
    )


def cli(*args, **kwargs):
    """Runs the hab cli. If an exception is raised, only the exception message
    is printed and the stack trace is hidden. Use `hab -v ...` to enable showing
    the entire stack trace.
    """
    try:
        return _cli(*args, **kwargs)
    except Exception:
        click.echo(f'{Fore.RED}Hab encountered an error:{Fore.RESET}')
        if _verbose_errors:
            # In verbose mode show the full traceback
            raise

        # Print the traceback message without the stack trace.
        click.echo(traceback.format_exc(limit=0))
        return 1


if __name__ == "__main__":
    cli()
