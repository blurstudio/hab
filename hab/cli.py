import logging
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

import click
from click.shell_completion import CompletionItem
from colorama import Fore

from . import Resolver, Site, __version__, utils
from .parsers.unfrozen_config import UnfrozenConfig

logger = logging.getLogger(__name__)


# No one wants to actually type `--help`
CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


def complete_alias(ctx, param, incomplete):
    """Dynamic tab completion for shell_complete generating available aliases"""
    resolver = ctx.obj.resolver
    if not ctx.obj.uri:
        # The URI hasn't been resolved, so don't have any aliases to return.
        return []
    # Resolve the config from the URI stored in `UriArgument.type_cast_value`.
    cfg = resolver.resolve(ctx.obj.uri)
    return [
        CompletionItem(alias)
        for alias in cfg.aliases
        if alias.strip().startswith(incomplete)
    ]


class UriArgument(click.Argument):
    """Accepts a URI string, frozen string or path to frozen json file.

    - If a frozen string or json file path is passed returns the unfrozen data
        dictionary.
    - If a uri is provided, the string is returned unmodified.
    - If a `-` is passed and the `prompt` kwarg is False, the `hab.user_prefs.UriObj`
        is returned and the command is responsible for resolving and saving the URI.
    - If a `-` is passed and user prefs are enabled, the stored uri in the
        current user's prefs is returned. If a stored uri is not resolved a
        UsageError is raised if required, or returned for later error handling.
        When using a user pref, a message is written to the error stream to
        ensure the user can see what uri was resolved. It is written to the error
        stream so it doesn't interfere with capturing output to a file(json).
    - If the timestamp on the .hab_user_prefs.json is lapse, the user will be
        prompted to address the out of date URI by entering a new path or using
        the already saved path.

    This also handles saving the provided uri to user prefs if enabled by
    `SharedSettings.enable_user_prefs_save`. This is only respected if an uri is
    provided. Ie if a frozen uri, json file or `-` are passed, prefs are not saved.

    Note: Using `err=True` so this output doesn't affect capturing of hab output from
    cmds like `hab dump - --format json > output.json `.

    Args:
        prompt (bool, optional): Controls how the special `-` URI is processed.
            if False then `hab.user_prefs.UriObj` is always returned via
            `resolver.user_prefs().uri_check()` and the click command is responsible
            for parsing the URI. Otherwise the stored user_pref is used or the
            `__uri_prompt` method is used to ask the user for a updated URI.
        **kwargs: Other click.Argument keyword arguments.
    """

    def __init__(self, *args, prompt=True, **kwargs):
        self.prompt = prompt
        # Override shell_complete with our implementation by default
        kwargs.setdefault("shell_complete", self.complete_uri)
        super().__init__(*args, **kwargs)

    def __uri_prompt(self, uri=None):
        """Wrapper function of click.prompt.
        Used to get a URI entry from the user"""
        if uri:
            response = click.prompt(
                "Please enter a new URI...\n"
                "Or press ENTER to reuse the expired URI:"
                f" [{Fore.LIGHTBLUE_EX}{uri}{Fore.RESET}]",
                default=uri,
                show_default=False,
                type=str,
                err=True,
            )
        else:
            response = click.prompt(
                "No URI exists.\nPlease Enter a URI", type=str, err=True
            )
        return response

    def complete_uri(self, ctx, param, incomplete):
        """Dynamic tab completion for shell_complete generating available URI's"""
        resolver = ctx.obj.resolver
        return [
            CompletionItem(uri.strip())
            for uri in resolver.dump_forest(resolver.configs)
            if uri.strip().startswith(incomplete)
        ]

    def type_cast_value(self, ctx, value):
        """Convert and validate the uri value. This override handles saving the
        uri to user prefs if enabled by the cli.
        """
        if value is None:
            result = click.UsageError("Missing argument 'URI'")
            if self.required:
                raise result
            return result
        # User wants to use saved user prefs for the uri
        if value == "-":
            uri_check = ctx.obj.resolver.user_prefs().uri_check()

            # If not using the prompt then just return the uri_check and allow
            # the click.command to handle resolving the URI.
            if not self.prompt:
                return uri_check

            # This will indicate that no user_pref.json was saved
            # and the user will be required to enter a uri path.
            if uri_check.uri is None:
                value = self.__uri_prompt()
                # Save a new .hab_user_prefs.json
                ctx.obj.resolver.user_prefs().uri = value
                click.echo("Saved hab user prefs", err=True)
                return value
            # Check if the saved .hab_user_prefs.json has an expire timestamp
            elif uri_check.timedout:
                logger.info(
                    f"{Fore.RED}Invalid 'URI' preference: {Fore.RESET}"
                    f"The saved URI {Fore.LIGHTBLUE_EX}{uri_check.uri}{Fore.RESET} "
                    f"has expired.",
                )
                # The uri is expired so lets ask the user for a new uri
                value = self.__uri_prompt(uri_check.uri)
                if value:
                    # Saving an updated .hab_user_prefs.json
                    ctx.obj.resolver.user_prefs().uri = value
                    click.echo("Saving hab user prefs", err=True)
                    return value
                else:
                    if self.required:
                        raise click.UsageError("A URI is required for Hab use.")
            # user_pref.json is found and its saved uri will be used
            else:
                click.echo(
                    f"Using {Fore.LIGHTBLUE_EX}{uri_check.uri}{Fore.RESET} "
                    "from hab user prefs",
                    err=True,
                )
                # Don't allow users to re-save the user prefs value when using
                # a user prefs value so they don't constantly reset the timeout.
                return uri_check.uri
        # User passed a frozen hab string
        if re.match(r"^v\d+:", value):
            return utils.decode_freeze(value)

        # If its not a string, convert to a Path object, if the path exists,
        # return the extracted dictionary assuming it was a json file.
        try:
            cpath = click.Path(path_type=Path, file_okay=True, resolve_path=True)
            data = cpath.convert(value, None, ctx=ctx)
            if data.exists():
                return utils.json.load(data.open())
        except ValueError:
            self.fail(f"{value!r} is not a valid frozen file path.", ctx)

        # Use standard click type casting on value.
        value = super().type_cast_value(ctx, value)

        # Save the uri to user prefs if requested. This should only happen if the
        # user actually provided a uri, not for other valid inputs on this class.
        if ctx.obj.enable_user_prefs_save:
            ctx.obj.resolver.user_prefs().uri = value

        # Store the URI so it can be used by other shell_complete functions.
        ctx.obj.uri = value

        return value


class UriHelpClass(click.Command):
    """Adds info about user prefs to the help text of commands that take a uri."""

    # Note: the leading whitespace is important to ensure the help text formats
    # correctly when merged with multi-line docstrings like activate.
    uri_text = """
    If you pass a dash `-` for URI, it will use the last URI you saved. You can
    update the saved uri by adding `--save-prefs` to a hab call. For example:
    `hab --save-prefs {subcmd} a/uri`.
    """
    timeout_text = (
        "The saved uri will periodically timeout requiring you to re-save your uri."
    )

    def get_help(self, ctx):
        prefs = ctx.obj.resolver.user_prefs()
        if prefs.enabled:
            self.help += f"\n\n{self.uri_text}".format(subcmd=self.name)
            # Only show timeout info if timeout is enabled
            if prefs.uri_timeout:
                self.help += self.timeout_text
        return super().get_help(ctx)


class SharedSettings(object):
    def __init__(
        self,
        site_paths=None,
        verbosity=0,
        script_dir=None,
        script_ext=None,
        prereleases=None,
        forced_requirements=None,
        dump_scripts=False,
        enable_user_prefs=None,
        enable_user_prefs_save=False,
        cached=True,
    ):
        self.verbosity = verbosity
        self.script_dir = Path(script_dir or ".").resolve()
        self.script_ext = script_ext
        self._resolver = None
        self.prereleases = prereleases
        self.forced_requirements = forced_requirements
        self.dump_scripts = dump_scripts
        self.site_paths = site_paths if site_paths else []
        self.enable_user_prefs = enable_user_prefs
        self.enable_user_prefs_save = enable_user_prefs_save
        self.cached = cached

    @classmethod
    def log_context(cls, uri):
        """Writes a logger.info call for the given uri string or dictionary."""
        if isinstance(uri, dict):
            logger.info("Context: {}".format(uri["uri"]))
        else:
            logger.info("Context: {}".format(uri))

    @property
    def resolver(self):
        if self._resolver is None:
            site = Site(self.site_paths)
            site.cache.enabled = self.cached
            self._resolver = Resolver(
                site=site,
                prereleases=self.prereleases,
                forced_requirements=self.forced_requirements,
            )
            self._resolver.dump_scripts = self.dump_scripts
            self._resolver.user_prefs().enabled = self.enable_user_prefs
        return self._resolver

    def write_script(
        self,
        uri,
        launch=None,
        exit=False,
        args=None,
        create_launch=False,
    ):
        """Generate the script the calling shell scripts expect to setup the environment"""
        self.log_context(uri)
        logger.debug(f"Script dir: {self.script_dir} ext: {self.script_ext}")

        if args:
            # convert to list, subprocess.list2cmdline does not like tuples
            args = list(args)

        if isinstance(uri, dict):
            # Load frozen json data instead of processing the URI
            cfg = UnfrozenConfig(uri, self.resolver)
        elif uri is None:
            # If a uri wasn't provided by the user raise the exception click
            # would have raised if uri didn't have `required=False`.
            raise click.UsageError("Missing argument 'URI'.")
        else:
            # Otherwise just process the uri like normal
            cfg = self.resolver.resolve(uri)

        if launch:
            _args = f" {' '.join(args)}" if args else ""
            launch_msg = f"Launching alias: {launch}{_args} for URI: {cfg.uri}"
        if self.script_dir:
            # Hab was called using the shell scripts, use them to launch the alias
            # using the same system as `hab launch - alias_name`. This allows the
            # python process used to parse the hab config to exit before the alias
            # is launched ensuring that if something kills python processes it won't
            # affect the launched alias or any host shells
            if launch:
                logger.info(f"{launch_msg} using shell.")
            cfg.write_script(
                self.script_dir,
                self.script_ext,
                launch=launch,
                exit=exit,
                args=args,
                create_launch=create_launch,
            )
        elif launch:
            # The shell scripts were not used, so we need to launch using a sub-process
            kwargs = {}
            # If using pythonw we won't get any cli output so it doesn't make sense
            # to keep this python instance open while the alias is running. Only block
            # if using the console version of python.
            blocking = not sys.executable.endswith("w.exe")
            if blocking:
                # When blocking, don't let the launcher redirect stdout/stderr so the
                # host shell can receive the output of this program in real time.
                # Note: This leaves the hab process running for the duration of
                # the launched alias. If something kills this python process
                # it may lead to odd output in the host shell.
                kwargs["stderr"] = None
                kwargs["stdout"] = None

            logger.info(f"{launch_msg} as subprocess.")
            proc = cfg.launch(launch, args, blocking=blocking, **kwargs)
            if blocking:
                sys.exit(proc.returncode)

    @classmethod
    def set_ctx_instance(cls, ctx, key, value):
        """Set a property on the SharedSetting instance for the given ctx,
        creating the instance if required.

        Args:
            ctx (click.Context): The context passed by click. Sets the requested
                key/value on ctx.obj. If obj isn't set it will create an instance.
            key (str or click.Option): The name of the SharedSettings property to modify.
            value (str): The value to store on key.
        """
        if isinstance(key, click.Option):
            key = key.name

        # Create the instance if it wasn't already created
        if ctx.obj is None:
            ctx.obj = cls()
        elif not isinstance(ctx.obj, SharedSettings):
            raise RuntimeError("Ctx.obj already set to an incompatible class.")

        setattr(ctx.obj, key, value)

        # If the resolver was already created, destroy it to ensure it gets
        # created with the updated options.
        if ctx.obj._resolver:
            # Let devs know if this gets called, ideally it never will be.
            logger.warning("[Optimization warning]: Resetting ctx resolver.")
            ctx.obj._resolver = None

        # Ensure logging settings are properly respected
        if key == "verbosity":
            global _verbose_errors

            if value > 2:
                value = 2
            _verbose_errors = bool(value)

            level = [logging.WARNING, logging.INFO, logging.DEBUG][value]
            logging.basicConfig(level=level)
        elif key == "logging_config":
            if value is not None:
                value = Path(value)
            utils.Platform.configure_logging(value)

        return value

    @property
    def site_paths(self):
        """A list of site json files used to define the Site as Path's."""
        return self._site_paths

    @site_paths.setter
    def site_paths(self, value):
        # Ensure the paths are converted to Path objects.
        self._site_paths = [Path(p) for p in value]


class SiteCommandLoader(click.Group):
    """Allows extending the hab cli by modifying the site config. You can add
    additional `click.Command` objects to the hab cli.

    For example if you add this to your site json file:
    `{"append": {"entry_points": {"hab.cli": {"gui": "hab_gui.cli:gui"}}}}`

    The "gui" key in the innermost dict is used for site resolution so another
    site json file can replace a upper level definition. As a general rule, the
    name should match the exposed click.command function.

    "hab_gui.cli:gui" defines what code to execute. For details on defining this,
    see value for `importlib-metadata.EntryPoints`. In practice this results in
    `from  hab_gui.cli import gui`.
    For the `hab.cli` entry points, its expected that the linked function(`gui`)
    is a `click.Command` object.
    """

    def _cli_entry_points(self, site):
        try:
            return self._ep_cache
        except AttributeError:
            # First call of this method, create the cache
            self._ep_cache = []

        # And populate the cache
        for ep in site.entry_points_for_group("hab.cli"):
            func = ep.load()
            self._ep_cache.append((ep, func))

        return self._ep_cache

    def list_commands(self, ctx):
        ret = super().list_commands(ctx)
        # Add any site defined entry_point commands
        for _, cmd in self._cli_entry_points(ctx.obj.resolver.site):
            ret.append(cmd.name)
        return sorted(ret)

    def get_command(self, ctx, name):
        # Find and use site defined entry_points commands
        for _, funct in self._cli_entry_points(ctx.obj.resolver.site):
            if name == funct.name:
                return funct
        # falling back to the commands defined by hab
        return super().get_command(ctx, name)


# This variable is used to keep track of the user enabled verbose hab output
# using `hab -v ...`. If they do, the full traceback is printed to the shell,
# otherwise just the last part of the traceback is printed so its easier to
# report and hopefully more descriptive.
_verbose_errors = False


# Establish CLI command group
@click.group(cls=SiteCommandLoader, context_settings=CONTEXT_SETTINGS)
@click.version_option(__version__, prog_name="hab")
@click.option(
    "--site",
    "site_paths",
    callback=SharedSettings.set_ctx_instance,
    # Note: Eager enables processing of site when generating help so it can
    # include commands defined by plugins.
    is_eager=True,
    multiple=True,
    # TODO: Implement a custom type that handles pathsep and respects env vars
    type=click.Path(file_okay=True, resolve_path=True),
    help="One or more site json files to load settings from. Uses the env var "
    "`HAB_PATHS` if not passed. The values in each file are merged into a single "
    "dict with the right most value of any given configuration option being used.",
)
@click.option(
    "-v",
    "--verbose",
    "verbosity",
    callback=SharedSettings.set_ctx_instance,
    count=True,
    # Note: Using eager makes it so logging is configured as early as possible
    # based on this argument.
    is_eager=True,
    help="Increase the verbosity of the output. Can be used up to 3 times. "
    "This also enables showing a full traceback if an exception is raised.",
)
@click.option(
    "--logging-config",
    callback=SharedSettings.set_ctx_instance,
    # Note: Using eager makes it so logging is configured as early as possible
    # based on this argument.
    is_eager=True,
    type=click.Path(file_okay=True, resolve_path=True),
    help="Path to json file defining a logging configuration based on "
    "logging.config.dictConfig. If not specified uses .hab_logging_prefs.json "
    "next to user prefs file if it exists.",
)
@click.option(
    "--script-dir",
    callback=SharedSettings.set_ctx_instance,
    type=click.Path(file_okay=False, resolve_path=False),
    help="This directory will contain the shell specific script files to enable "
    "this environment configuration.",
)
@click.option(
    "--script-ext",
    callback=SharedSettings.set_ctx_instance,
    help="The shell specific scripts created in script-dir will have this "
    "format and extension.",
)
@click.option(
    "--cache/--no-cache",
    "cached",
    callback=SharedSettings.set_ctx_instance,
    default=True,
    help="Allow per-site caching of configs and distros.",
)
@click.option(
    "--pre/--no-pre",
    "prereleases",
    callback=SharedSettings.set_ctx_instance,
    default=None,
    help="Include pre-releases when finding the latest distro version.",
)
@click.option(
    "-r",
    "--requirement",
    "forced_requirements",
    callback=SharedSettings.set_ctx_instance,
    multiple=True,
    help="Forces this distro requirement ignoring normally resolved requirements. Using "
    "this may lead to configuring your environment incorrectly, use with caution.",
)
@click.option(
    "--dump-scripts/--no-dump-scripts",
    callback=SharedSettings.set_ctx_instance,
    default=False,
    help=(
        "Print the generated scripts hab uses for this command instead of "
        "running them. This does not work for dump."
    ),
)
@click.option(
    "--prefs/--no-prefs",
    "enable_user_prefs",
    callback=SharedSettings.set_ctx_instance,
    default=None,
    help="If you don't pass a URI, allow looking it up from user prefs.",
)
@click.option(
    "--save-prefs/--no-save-prefs",
    "enable_user_prefs_save",
    callback=SharedSettings.set_ctx_instance,
    default=None,
    help="Update the uri stored in prefs if the uri is provided.",
)
@click.pass_context
def _cli(ctx, **kargs):
    # Note: Using the `set_ctx_instance` callback on the options prevents
    # the need to process anything inside of this function.
    pass


# set uri command
@_cli.command()
@click.argument("uri", required=False)
@click.pass_obj
def set_uri(settings, uri):
    """Allows for saving a local URI default by passing
    a URI argument.  If no argument is passed uri-set
    will prompt you to enter and argument."""
    settings.log_context(uri)
    current_uri = settings.resolver.user_prefs().uri
    if uri is None:
        uri = click.prompt(
            "Please enter a URI value"
            f"[{Fore.LIGHTBLUE_EX}{current_uri}{Fore.RESET}]",
            default=current_uri,
            show_default=False,
            type=str,
            err=True,
        )
    click.echo(f"\nSetting default URI to: {Fore.LIGHTBLUE_EX}{uri}{Fore.RESET}\n")
    settings.resolver.user_prefs().uri = uri


# env command
@_cli.command(cls=UriHelpClass)
@click.argument("uri", cls=UriArgument)
@click.option(
    "-l",
    "--launch",
    default=None,
    help="Run this alias after activating. This leaves the new shell active.",
    # TODO: This requires resolving the uri argument before this option. Click
    # doesn't support that by default. Figure out how to get this working.
    # shell_complete=complete_alias,
)
@click.pass_obj
def env(settings, uri, launch):
    """Configures and launches a new shell with the resolved setup."""
    settings.write_script(uri, create_launch=True, launch=launch)


# dump command
@_cli.command(cls=UriHelpClass)
# For specific report_types uri is not required. This is manually checked in
# the code below where it raises `uri_error`.
@click.argument("uri", required=False, cls=UriArgument)
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
        ["nice", "site", "s", "uris", "u", "versions", "v", "forest", "f", "all-uris"]
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
    "-f",
    "--format",
    "format_type",
    type=click.Choice(["nice", "freeze", "json", "versions"]),
    default="nice",
    help="Choose how the output is formatted.",
)
def dump(settings, uri, env, env_config, report_type, flat, verbosity, format_type):
    """Resolves and prints the requested setup."""

    # Convert uri argument to handle if a uri was not provided/loaded
    uri_error = None
    if isinstance(uri, click.UsageError):
        uri_error = uri
        uri = None

    settings.log_context(uri)
    # Convert report_tupe short names to long names for ease of processing
    report_map = {"u": "uris", "v": "versions", "f": "forest", "s": "site"}
    report_type = report_map.get(report_type, report_type)

    resolver = settings.resolver

    if report_type in ("uris", "versions", "forest"):
        # Allow the user to disable truncation of versions with verbosity flag
        truncate = None if verbosity else 3

        def echo_line(line):
            if line.strip() == line:
                click.echo(f"{Fore.GREEN}{line}{Fore.RESET}")
            else:
                click.echo(line)

        if report_type in ("uris", "forest"):
            click.echo(f'{Fore.YELLOW}{" URIs ".center(50, "-")}{Fore.RESET}')
            # Filter out any URI's hidden by the requested verbosity level
            with utils.verbosity_filter(resolver, verbosity):
                for line in resolver.dump_forest(resolver.configs):
                    echo_line(line)
        if report_type in ("versions", "forest"):
            click.echo(f'{Fore.YELLOW}{" Versions ".center(50, "-")}{Fore.RESET}')
            for line in resolver.dump_forest(
                resolver.distros,
                attr="name",
                truncate=truncate,
            ):
                echo_line(line)
    elif report_type == "all-uris":
        # Combines all non-placeholder URI's into a single json document and display.
        # This can be used to compare changes to configs when editing them in bulk.
        ret = resolver.freeze_configs()
        ret = utils.dumps_json(ret, indent=2)
        click.echo(ret)
    elif report_type == "site":
        click.echo(resolver.site.dump(verbosity=verbosity))
    else:
        if isinstance(uri, dict):
            # Load frozen json data instead of processing the URI
            ret = UnfrozenConfig(uri, resolver)
        elif uri_error:
            # If the user didn't choose a report type that doesn't require a uri
            # and a uri wasn't specified, raise a UsageError  similar to the one
            # click normally raises. UriArgument likely has augmented the
            # exception to make it easier to debug the issue.
            raise uri_error
        elif flat:
            ret = resolver.resolve(uri)
        else:
            ret = resolver.closest_config(uri)

        # This is a seperate set of if/elif/else statements than from above.
        # I became confused while reading so decided to add this reminder.
        if format_type == "freeze":
            ret = utils.encode_freeze(ret.freeze(), site=resolver.site)
        elif format_type == "json":
            ret = utils.dumps_json(ret.freeze(), indent=2)
        elif format_type == "versions":
            ret = "\n".join([v.name for v in ret.versions])
        else:
            ret = ret.dump(
                environment=env, environment_config=env_config, verbosity=verbosity
            )

        click.echo(ret)


# activate command
@_cli.command(cls=UriHelpClass)
@click.argument("uri", cls=UriArgument)
@click.option(
    "-l",
    "--launch",
    default=None,
    help="Run this alias after activating. This leaves the new shell activated.",
    # TODO: This requires resolving the uri argument before this option. Click
    # doesn't support that by default. Figure out how to get this working.
    # shell_complete=complete_alias,
)
@click.pass_obj
def activate(settings, uri, launch):
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

    settings.write_script(uri, launch=launch)


# launch command
@_cli.command(
    context_settings=dict(
        ignore_unknown_options=True,
    ),
    cls=UriHelpClass,
)
@click.argument("uri", cls=UriArgument)
@click.argument("alias", shell_complete=complete_alias)
# Pass all remaining arguments to the requested alias
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_obj
def launch(settings, uri, alias, args):
    """Configure and launch an alias without modifying the current shell. The
    first argument is a URI, The second argument is the ALIAS to launch. Any
    additional arguments are passed as launch arguments to the alias. Note, if
    using bash on windows you may need to pass file paths correctly for bash as
    any quotes used may not make it to the alias launch arguments. (ie: '/c/Program\\ Files').
    """
    settings.write_script(uri, create_launch=True, launch=alias, exit=True, args=args)


# Cache command
@_cli.command()
@click.argument("path", type=click.Path(file_okay=True, resolve_path=True))
@click.pass_obj
def cache(settings, path):
    """Create/update the cache for a given site file. The path argument is the
    site config file. To allow for cross-platform support you should make sure
    you are loading the same site configuration that will be used by this cache
    or at least a site configuration that defines the same `platform_path_maps`.
    """
    path = Path(path)
    click.echo(f"Caching: {path}")
    s = datetime.now()
    out = settings.resolver.site.cache.save_cache(settings.resolver, path)
    e = datetime.now()
    click.echo(f"Cache took: {e - s}, cache file: {out}")


def cli(*args, **kwargs):
    """Runs the hab cli. If an exception is raised, only the exception message
    is printed and the stack trace is hidden. Use `hab -v ...` to enable showing
    the entire stack trace.
    """
    try:
        return _cli(*args, **kwargs)
    except Exception:
        click.echo(f"{Fore.RED}Hab encountered an error:{Fore.RESET}")
        if _verbose_errors or sys.excepthook != sys.__excepthook__:
            # If a plugin has replaced sys.excepthook it likely want's to handle
            # how the traceback is handled.
            # Ensure the full traceback is shown when in verbose mode.
            raise

        # Otherwise print the traceback message without the stack trace.
        click.echo(traceback.format_exc(limit=0))
        return 1


if __name__ == "__main__":
    cli()
