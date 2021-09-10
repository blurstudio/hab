import click
from . import Resolver
import logging
import os

logger = logging.getLogger(__name__)


# No one wants to actually type `--help`
CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


class SharedSettings(object):
    def __init__(
        self,
        configs=None,
        distros=None,
        verbosity=0,
        file_config=None,
        file_launch=None,
        pre=False,
    ):
        self.verbosity = verbosity
        self.file_config = os.path.abspath(file_config or ".")
        self.file_launch = os.path.abspath(file_launch or ".")
        self.config_paths = configs
        self.distro_paths = distros
        self._resolver = None
        self.prereleases = pre

    @property
    def resolver(self):
        if self._resolver is None:
            self._resolver = Resolver(
                self.config_paths, self.distro_paths, prereleases=self.prereleases
            )
        return self._resolver

    def write_script(self, uri, launch_script=False, launch=None, exit=False):
        """Generate the script the calling shell scripts expect to setup the environment"""
        logger.info("Context: {}".format(uri))
        logger.debug("Script: {}".format(self.file_config))

        file_launch = None
        if launch_script:
            file_launch = self.file_launch
            logger.debug("Launch script: {}".format(file_launch))

        ret = self.resolver.resolve(uri)
        ret.write_script(self.file_config, file_launch, launch=launch, exit=exit)


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option(
    "-c",
    "--configs",
    multiple=True,
    type=click.Path(file_okay=False, resolve_path=True),
    help="glob paths to find configuration. Uses the env var `HAB_CONFIG_PATHS` "
    "if not passed.",
)
@click.option(
    "-d",
    "--distros",
    multiple=True,
    type=click.Path(file_okay=False, resolve_path=True),
    help="glob paths to find distro configuration. Uses the env var `HAB_DISTRO_PATHS` "
    "if not passed.",
)
@click.option(
    "-v",
    "--verbose",
    "verbosity",
    count=True,
    help="Increase the verbosity of the output. Can be used up to 3 times.",
)
@click.option(
    "--file-config",
    type=click.Path(dir_okay=False, resolve_path=False),
    help="This file will contain the shell specific configuration commands to enable"
    "this environment configuration.",
)
@click.option(
    "--file-launch",
    type=click.Path(dir_okay=False, resolve_path=False),
    help="This file will contain the shell specific launching command to call file-config.",
)
@click.option(
    "--pre/--no-pre",
    default=True,
    help="Include pre-releases when finding the latest distro version.",
)
@click.pass_context
def cli(ctx, configs, distros, verbosity, file_config, file_launch, pre):
    ctx.obj = SharedSettings(configs, distros, verbosity, file_config, file_launch, pre)
    if verbosity > 2:
        verbosity = 2
    level = [logging.WARNING, logging.INFO, logging.DEBUG][verbosity]
    logging.basicConfig(level=level)


@cli.command()
@click.argument("uri")
@click.option(
    "-l",
    "--launch",
    default=None,
    help="Run this alias after activating. This leaves the new shell active.",
)
@click.pass_obj
def env(settings, uri, launch):
    """Configures and launches a new shell with the resolved setup."""
    settings.write_script(uri, launch_script=True, launch=launch)


@cli.command()
@click.argument("uri")
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
    type=click.Choice(["config", "c", "forest", "f"]),
    default="config",
    help="Type of report.",
)
@click.option(
    "--flat/--no-flat",
    default=True,
    help="Flatten the resolved object",
)
def dump(settings, uri, env, env_config, report_type, flat):
    """Resolves and prints the requested setup."""
    logger.info("Context: {}".format(uri))
    if report_type in ("forest", "f"):
        click.echo(" Configs ".center(50, "-"))
        click.echo(settings.resolver.dump_forest(settings.resolver.configs))
        click.echo(" Distros ".center(50, "-"))
        click.echo(settings.resolver.dump_forest(settings.resolver.distros))
    else:
        if flat:
            ret = settings.resolver.resolve(uri)
        else:
            ret = settings.resolver.closest_config(uri)

        click.echo(ret.dump(environment=env, environment_config=env_config))


@cli.command()
@click.argument("uri")
@click.option(
    "-l",
    "--launch",
    default=None,
    help="Run this alias after activating. This leaves the new shell activated.",
)
@click.pass_obj
def activate(settings, uri, launch):
    """Resolves the setup and updates in the current shell.

    In powershell and bash you must use the source dot: ". hab activate ..."
    """
    settings.write_script(uri, launch=launch)


@cli.command()
@click.argument("uri")
@click.argument("alias")
@click.pass_obj
def launch(settings, uri, alias):
    """Configure and launch an alias without modifying the current shell."""
    settings.write_script(uri, launch_script=True, launch=alias, exit=True)


if __name__ == "__main__":
    cli()
