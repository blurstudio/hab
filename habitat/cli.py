import click
from . import Resolver
import json
import logging
import os

logger = logging.getLogger(__name__)


# No one wants to actually type `--help`
CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


class SharedSettings(object):
    def __init__(self, paths=(), verbosity=0, script_output=None):
        self.verbosity = verbosity
        self.script_output = os.path.abspath(script_output or ".")
        # set HABITAT_PATH=H:\public\mikeh\simp\habitat_cfgs\config;H:\public\mikeh\simp\habitat_cfgs\config\projectDummy
        self.paths = paths


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option(
    "-p",
    "--paths",
    multiple=True,
    type=click.Path(file_okay=False, resolve_path=True),
    help="paths to find json files.",
)
@click.option(
    "-v",
    "--verbose",
    "verbosity",
    count=True,
    help="Increase the verbosity of the output. Can be used up to 3 times.",
)
@click.option(
    "--script-output",
    type=click.Path(dir_okay=False, resolve_path=True),
    help="The commands that generate an OS specific script to configure the environment will write to this location.",
)
@click.pass_context
def cli(ctx, paths, verbosity, script_output):
    ctx.obj = SharedSettings(paths, verbosity)
    if verbosity > 2:
        verbosity = 2
    level = [logging.WARNING, logging.INFO, logging.DEBUG][verbosity]
    logging.basicConfig(level=level)


@cli.command()
@click.argument("uri")
@click.pass_obj
def env(settings, uri):
    """Configures and launches rez with the resolved blur setup."""
    uri = uri.strip(":").split(":")

    logger.info("Context: {}".format(uri))
    logger.info("Paths: {}".format(settings.paths))
    ret = Resolver(settings.paths).resolve(uri)
    ret = json.dumps(ret, indent=2)
    click.echo(ret)


@cli.command()
@click.argument("uri")
@click.pass_obj
def activate(settings, uri):
    """Resolves the blur setup and sets environment variables in the current
    shell so you can manually. Modify and tweak them the launch rez.
    """
    click.echo("Not implemented")


if __name__ == "__main__":
    cli()
