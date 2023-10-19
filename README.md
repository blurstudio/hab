# Hab

A launcher that lets you configure software distributions and how they are consumed with
dependency resolution. It provides a habitat for you to work in.

Features:

* [URI](#URI) based configuration resolution with inheritance. Makes it easy to define
generic settings, but override for child URIs.
* Simple [configuration](#configuration) with json files.
* Site configuration, code distributions are separate from URI configurations. All of
these use a common json schema.
* Flexible site configuration with a minimum of environment variables.
* No long running python processes. The hab cli uses a shell specific script instead
of a setuptools exe. This prevents some strange behavior in the shell if the python
process is killed without exiting the new shell that python launched.
* Can modify the existing shell similar to how virtualenv's activate script works.
* Simple distribution of versions. Should not require updating of checked in files
to release a unique distro version.
* Easy developer testing. A developer can additional site configurations for their host.
A git checkout can be found and the version of a distro can be dynamically generated
using setuptools_scm, or explicitly set by adding a `.hab_version.txt` that is not
committed to the repo.

# Quickstart

## Using hab

The general workflow for using hab is to use `hab env` to configure your shell, then
launch one or more aliases to work in. When done with that environment you exit it
with the shells exit command. Then you can enable another hab config with a
different URI.

You should be choosing the correct URI for your current task. This makes it so if
required the underlying configuration for each task you are working on can be
configured you don't need to know that something was changed.

#### Bash (Linux and Windows)

```bash
$ hab env project_a/Seq001/S0010     # Enable this environment
[project_a/Seq001/S0010] $ maya      # Launch a hab defined alias
[project_a/Seq001/S0010] $ houdini   # Launch a hab defined alias
[project_a/Seq001/S0010] $ exit      # Exit out of the current hab environment
$                                    # Back at the original shell without hab config
$ hab env project_a/Seq001/S0020     # Switch to another task with its own config ...
```

#### Command Prompt (Windows)

```batch
C:\>hab env project_a/Seq001/S0010      # Enable this environment
[project_a/Seq001/S0010] C:\>maya       # Launch a hab defined alias
[project_a/Seq001/S0010] C:\>houdini    # Launch a hab defined alias
[project_a/Seq001/S0010] C:\>exit       # Exit out of the current hab environment
C:\>                                    # Back at the original shell without hab config
C:\>hab env project_a/Seq001/S0020      # Switch to another task with its own config ...
```

#### PowerShell  (Windows)

```ps1
PS C:\> hab env project_a/Seq001/S0010  # Enable this environment
[project_a/Seq001/S0010] C:\>maya       # Launch a hab defined alias
[project_a/Seq001/S0010] C:\>houdini    # Launch a hab defined alias
[project_a/Seq001/S0010] C:\>exit       # Exit out of the current hab environment
PS C:\>                                 # Back at the original shell without hab config
PS C:\> hab env project_a/Seq001/S0020  # Switch to another task with its own config ...
```

In the above examples the user is enabling the hab environment for the
URI:`project_a/Seq001/S0010`, then launching the Maya and Houdini aliases.
Finally they are exiting the current URI so they can enable another URI. The user
doesn't need to worry about which version of the Maya or Houdini applications they
should launch, that is configured for them by the URI they pass to `hab env`.

### Looking up aliases

In the previous section the use knew that they could run maya and houdini. You can
lookup the aliases for a given URI with the `hab dump` command. An alias is a hab
controlled way to launch a application.

```bash
$ hab dump project_a/Seq001/S0010
Dump of FlatConfig('project_a')
------------------------------------------------------
aliases:  maya mayapy pip houdini houdini18.5
------------------------------------------------------
```

This shows that a user has access to `maya`, `mayapy`, `pip`, `houdini`, and
`houdini18.5` aliases. For this config the `houdini` and `houdini18.5` aliases
end up launching the same application, See [Multiple app versions](#multiple-app-versions)

### User Prefs

To support reusable alias shortcuts, hab has the ability to remember a URI and
reuse it for the next run. Anywhere you pass a URI to the cli, you can pass a
dash `-` instead. Hab will use the saved URI.

```bash
$ hab env -
```

This feature has to be enabled by the site configuration. Depending on the site config
you may need to enable it by adding `--prefs` after `hab`.
```bash
hab --prefs dump -
```

The site configuration may also configure a timeout that will require you to re-specify
the URI after a while.

If you try to use `-` with an expired URI, Hab will notify you and prompt you to re-specify a URI.

To update the URI manually, pass `--save-prefs` after hab. You can
not use `-` when using this option.
```bash
hab --save-prefs dump project_a/Seq001/S0010
```

## Installing

Hab is installed using pip. It requires python 3.6 or above. It's recommended
that you add the path to your python's bin or Scripts folder to the `PATH`
environment variable so you can simply run the `hab` command.

```
pip3 install hab
```

If you want to make use of [json5](https://pypi.org/project/pyjson5/) formatting
when creating the various json files that drives hab, you should use the optional
json5 dependency. This lets you add comments and allows for trailing commas.

```
pip3 install hab[json5]
```

Once hab is installed you need to point it to one or more [site configurations](#site)
using the HAB_PATHS environment variable. Each shell/platform assigns environment
variables differently. These set the env variable for the current shell only.

#### Bash (Linux)

```bash
export HAB_PATHS="/path/to/site_b.json:/path/to/site_a.json"
```

#### Bash (Windows, cygwin)

You can use windows style paths by adding double quotes around the path(s). If
specifying a unc path with backslashes, you need to escape the leading slashes,
but can leave the remaining backslashes(when double quoted). Use `;` for the pathsep.
```bash
export HAB_PATHS="c:\path\to\site_b.json;/c/path/to/site_a.json;\\\\server\share\path\to\site_a.json"
```

#### Command Prompt (Windows)

```batch
set "HAB_PATHS=c:\path\to\site_b.json;/c/path/to/site_a.json"
```

#### PowerShell (Windows)

```ps1
$env:HAB_PATHS="c:\path\to\site_b.json;c:\path\to\site_a.json"
```

# Hab Developer Quickstart

Hab has some code quality automated checks and extensive unit testing setup. When
contributing, you should make sure your changes match the flake8 rules and follow
the configured [black](https://github.com/psf/black) formatting.

## pre-commit hooks

It's recommended that you install the configured
[pre-commit](https://pre-commit.com/#3-install-the-git-hook-scripts) hooks.
These test for and fix black and flake8 issues as well as other file checks.

Use pip to install pre-commit if it's not already installed.
```
pip3 install pre-commit
```
Install the hab configuration of pre-commit hooks to enable them when using git.
Run this from the root of your git checkout.
```
pre-commit install
```

From this point forward when you commit changes using git, it will pre-validate
and fix most code quality issues. Those changes are not staged so you can inspect
the changes it makes.

## tox

We use tox to do all unit tests using pytest and also run black and flake8 code
quality checks. You should use tox before you push your code changes to ensure
that your tests will pass when running on github.


Install tox if its not already installed:
```
pip3 install tox
```

To run all tests. Make sure to run tox from the root of your git checkout:
```
tox
```

Examples of running specific tests:
- `tox -e py37-json`  Run just the py37-json test
- `tox -e py39-json5`  Run just the py39-json5 test
- `tox -e begin,py37-json,end`  Show code coverage report for just this test
- `tox -e flake8`  Run the flake8 tests
- `tox -e begin,py37-json,end -- -vv`  Enables verbose mode for pytest. Any text after `--` is passed as cli arguments passed to pytest

# Overview

## URI

`identifier1/identifier2/...`

You specify a configuration using a simple URI of identifiers separated by a `/`.
Currently hab only supports absolute URI's.

Examples:
* projectDummy/Sc001/S0001.00
* projectDummy/Sc001/S0001.00/Animation
* projectDummy/Thug
* default

If the provided URI has no configurations provided, the default configuration is used.
This also supports inheritance with some special rules, see
[config inheritance](#config-inheritance) for more details.

The provided URI is always stored in the `HAB_URI` environment variable.

## CLI

Hab is designed as an api with cli support. The majority of the actual work is
done by the api so it can be used with the provided cli, or can be customized by import.
A gui version of the cli is planned in the future as a second pip package.

1. `hab env`: The env command launches a new shell configured by hab. You can exit
the shell to return to the original configuration. This is how most users will interact
with hab in the command line.
2. `hab activate`: Updates the current shell with the hab configuration. This is
similar to activating a virtualenv, but currently there is no way to deactivate. This is
mostly how scripts can make use of hab.
3. `hab dump`: Formats the resolved configuration and prints it. Used for debugging
configurations and listing the commands available.
4. `hab launch`: A shortcut for `hab env --launch [alias]`, but automatically exits the
configured shell when the launched application exits. Returning you to your existing
shell without modification. Useful for quickly testing changes to a configuration
requiring a running an application.
5. `hab set-uri`: A command that allows the user to set a default URI. This default will be
used with the dash `"-"` flag, which allows the user to quickly recall the saved URI.
A argument can be passed to directly set the default. Alternatively, it can be run with no
argument which will provide a prompt for the user to enter a URI. This method will display
any currently saved URI for reference.

Examples:

```bash
$ hab env projectDummy
$ hab env projectDummy/Thug
```

The cli prompt is updated while inside a hab config is active. It is `[URI] [cwd]`
Where URI is the URI requested and cwd is the current working directory.

## Restoring resolved configuration

Under normal operation hab resolves the configuration it loads each time it is run.
This makes it easy to get updates to the configuration by re-launching hab. However,
if you want to load the same hab configuration at a later date or on another computer
it's possible a new distro version has been released or some config settings have
been modified. For example if you submit a render job to the farm, you want every
frame to render using the same hab configuration not what ever it happens to
resolve for that launch.

To handle this the hab cli stores the current configuration in the `HAB_FREEZE`
environment variable. You can even use a frozen config on other platforms as long
as you properly configure `platform_path_maps` in your site config.

The cli can be used to export these freezes. This example uses the cli to save a
freeze to disk as json using dump using `--format json`.
```bash
hab dump projectDummy --format freeze > /tmp/frozen_config.json
```

And to restore that frozen config from the json file. This works for commands
other than `dump`.
```bash
hab dump --unfreeze /tmp/frozen_config.json
```

Similarly you can save/load the encoded freeze string using `--format freeze`.
This is what is stored in the `HAB_FREEZE` environment variable.

```bash
export frozen_config=$(hab dump app/nuke13 -f freeze)
hab dump --unfreeze $frozen_config
```

A freeze string is prefixed with `vX:` to denote the version of freeze it was
encoded with. See `hab.utils.encode_freeze` and `hab.utils.decode_freeze` to
encode/decode each version of freeze strings.

You can configure what version of freeze string is saved in `HAB_FREEZE` by
setting the `freeze_version` key in your site json configuration. This should be
an int value or None. If not specified(ie None), then the default version is used.

```json
{"set": {"freeze_version": 1}}
```

## API

TODO

## Configuration

Hab is configured by json files found with glob strings passed to the cli or defined
by an environment variable.


### Duplicate definitions

The general rule for when hab encounters duplicated definitions is that the first
encountered object is used and any duplicates are ignored. Here are some examples
that follow that rule and links to details:

* **Aliases:** [Multiple app versions](#multiple-app-versions)
* **Entry Points:** [Hab Entry Points](#hab-entry-points)
* **Site:** [Site](#site)

`config_paths` and `distro_paths` have [more complex rules](#common-settings).


### Site

Hab uses the `HAB_PATH` environment variable to point to one or more site
configuration files. If the `--site` option is passed to the cli, it is used instead of
the environment variable.

Each of the file paths specified are read and merged into a single site configuration
dictionary hab uses. When using multiple site json files here are some general
rules to keep in mind.

1. The left most site configuration takes precedence for a given item.
2. For prepend/append operations on lists, the left site file's paths will placed
on the outside of the the right site file's paths.
3. For `platform_path_maps`, only the first key is kept and any duplicates
are discarded.

See [Defining Environments](#defining-environments) for how to structure the json
to prepend, append, set, unset values.

Developers can use this to load local site configurations loading their wip code
instead of the official releases. See [TestResolvePaths::test_paths](tests/test_site.py)
to see an example of [overriding](tests/site_override.json) the
[main](tests/site_main.json) site settings.

You can inspect the site settings by using the `hab dump -t s` or
`hab dump --type site` cli command. See
[TestMultipleSites::test_left_right and TestMultipleSites::test_right_left](tests/test_site.py)
for an example of how these rules are applied. Here is a dump of the final result
of using all [3 site json files](tests/site).
```bash
$ cd tests/site
$ hab --site site_left.json --site site_middle.json --site site_right.json dump --type site -v
Dump of Site
-------------------------------------------------------------------
HAB_PATHS:  C:\blur\dev\hab_\tests\site\site_left.json
            C:\blur\dev\hab_\tests\site\site_middle.json
            C:\blur\dev\hab_\tests\site\site_right.json
config_paths:
distro_paths:
ignored_distros:  release, pre
platforms:  windows, osx, linux
set_value:  left
test_paths:  left_prepend
             middle_prepend
             right_prepend
             right_append
             middle_append
             left_append
platform_path_maps:  host:  linux:  host-linux_left
                                     windows:  host-windows_left
                     mid:  linux:  mid-linux_middle
                           windows:  mid-windows_middle
                     net:  linux:  net-linux_right
                           windows:  net-windows_right
                     shared:  linux:  shared-linux_left
                              windows:  shared-windows_left
-------------------------------------------------------------------
```
Note the order of left/middle/right in the test_paths variable. Also, for
`platform_path_maps`, `host` is defined in all 3 site files, but only the first
site file with it defined is used. The other path maps are picked up from the
site file they are defined in.

#### Hab Entry Points

The site file can be used to replace some hab functionality with custom plugins.
These are defined in site files with the "entry_points" dictionary.

[Example](tests/site/site_entry_point_a.json) site json entry_point config.
```json5
{
    "prepend": {
        "entry_points": {
            // Group
            "cli": {
               // Name: Object Reference
               "gui": "hab_test_entry_points:gui"
            }
        }
    }
}
```
See the [Entry points specification data model](https://packaging.python.org/en/latest/specifications/entry-points/#data-model)
for details on each item.

| Feature | Description | Multiple values |
|---|---|---|
| cli | Used by the hab cli to add extra commands | All unique names are used. |
| launch_cls | Used as the default `cls` by `hab.parsers.Config.launch()` to launch aliases from inside of python. This should be a subclass of subprocess.Popen. A [complex alias](#complex-aliases) may override this per alias. Defaults to [`hab.launcher.Launcher`](hab/launcher.py). [Example](tests/site/site_entry_point_a.json) | Only the first is used, the rest are discarded. |

The name of each entry point is used to de-duplicate results from multiple site json files.
This follows the general rule defined in [duplicate definitions](#duplicate-definitions).

### Python version

Hab uses shell script files instead of an entry_point executable. This allows it
to modify the existing shell(see `hab activate`). This has a small drawback of needing
to know what version of python to call. It relies on the assumption that you are using
hab with the default python 3 install. For example that you can call `python3 -m hab`
or `py -3 -m hab` on windows. Here is a breakdown of how the python call is built by
the scripts:

1. If the `HAB_PYTHON` env var is set, its value is always used.
2. If a virtualenv is active, the `python` command is used.
3. Otherwise on linux `python3` is used, and on windows `py -3` is used.

#### Common settings

* `colorize`: If `hab dump` should colorize its output for ease of reading.
* `config_paths`: Configures where URI configs are discovered. See below.
* `distro_paths`: Configures where distros discovered. See below.
* `platform_path_maps`: Configures mappings used to convert paths from one
operating system to another. This is used by the freeze system to ensure that if
unfrozen on another platform it will still work.
* `platforms`: A list of platforms that are supported by these hab configurations.
When using freeze, all of these platforms will be stored. Defaults to linux, osx, windows.
* `prereleases`: If pre-release distros should be allowed. Works the same as
`pip install --pre ...`.
* `prefs_default`: Controls if [user prefs](#user-prefs) can be used and if they
are enabled by default. Ie if you can pass `-` for a URI. If this is set to
`disabled`(the default), user prefs can not be used. If set to `--prefs`, then
user prefs are enabled by default. Conversely, if set to `--no-prefs` then user
prefs are disabled by default. Users can pass either of these cli flags to hab
to override the default(as long as its not disabled.) `hab --prefs dump ...`.
* `prefs_uri_timeout`: If a URI [user preference](#user-prefs) was set longer
than this duration, force the user to re-save the URI returned for `-` when using
the `--save-prefs` flag. To enable a timeout set this to a dictionary of kwargs
to initialize a `datetime.timedelta` object.

`config_paths` and `distro_paths` take a list of glob paths. For a given glob
string in these variables you can not have duplicate values. For configs a
duplicate is two configs with the same URI. A duplicate distro is two distros
with the same name and version. If this happens a `DuplicateJsonError` is raised.
This prevents developers from copying a config and forgetting to update its context.

You can however have duplicates across individual glob paths. The glob paths are processed
left to right and the first config/distro is used, any subsequent duplicates are ignored
and a warning is logged to aid in debugging. This feature allows a developer to add any
git checkouts they are working on that will be used, but still have access to all of the
global shared configs/distros they are not working on.
See [specifying distro version](#specifying-distro-version) for details on specifying a
distro version in a git repo.

`platform_path_maps` is a dictionary, the key is a unique name for each mapping,
and value is a dictionary of leading paths for each platform. The unique name
allows for multiple site json files to override the setting. If multiple site
json files specify the same key, the right-most site json file specifying that
key is used.

```json
{
    "append": {
        "platform_path_maps": {
            "server-main": {
                "linux": "/mnt/main",
                "windows": "\\\\example\\main"
            },
            "server-dev": {
                "linux": "/mnt/dev",
                "windows": "\\\\example\\dev"
            }
        }
    },
    "set": {
        "platforms": ["linux", "windows"]
    }
}
```

With these settings, if a path on a linux host, starts with `/mnt/main` when
generating the corresponding windows file path it will translate it to
`\\example\main`. Note the use of `platforms` to disable osx platform support.

### Distro

A distro defines a application, distribution or plugin that has multiple versions. It
is mostly used to define aliases and environment variables. It can also define
additional requirements.

A recommended released distro folder structure: `[name]\[version]\.hab.json`.
The `[name]` folder is referenced by one of the disto_path globs. This makes it easy
to store multiple versions of the distro. Each glob specified by `distro_paths` will
automatically have `/*/.hab.json` added to it, so the `.hab.json` file should
be in the root of a version folder. The root of the version folder is likely the root of
a git repo.

Example .hab.json:
```json
{
    "name": "maya2020",
    "version": "2020.1",
    "environment": {
        "append": {
            "MAYA_MODULE_PATH": "{relative_root}"
        }
    },
    "aliases": {
        "windows": [
            ["maya", "C:\\Program Files\\Autodesk\\Maya2020\\bin\\maya.exe"],
            ["mayapy", "C:\\Program Files\\Autodesk\\Maya2020\\bin\\mayapy.exe"]
        ]
    }
}

```

In most cases  you will not define version in `.hab.json`. If not defined, the
parent folder is used as the version. This makes it easy for automated deployments
without needing to modify a file checked into version control.

##### Multiple app versions

You will note that we are using the version of maya in name. This allows you to
provide access to multiple versions of the Maya application. Only one version of
a given distro name is going to be used so if you need access to multiple versions
of maya you must use this method. If an duplicate alias is defined, it is ignored.
The order distros are specified controls which duplicate alias is used, so make
sure the distro you want to use for a generic alias is specified before the others.
See [app/houdini/a](tests/configs/app/app_houdini_a.json) and
[app/houdini/b](tests/configs/app/app_houdini_b.json) for an example of how this
is controlled. Both of these configs end up adding the aliases `houdini`,
`houdini18.5` and `houdini19.5`, but the `houdini` alias is configured differently.

#### Specifying distro version

There are a few ways to define a distro version, they are provided to make deployment
and development testing easy. Here is the 4 ways to define the version of a distro, the
first one found is used.

1. The version property in `.hab.json`. This has some drawbacks, `.hab.json` is
likely checked into version control so modifying this requires committing changes to
the repo, or working copy changes you have to maintain.
2. A `.hab_version.txt` file next to `.hab.json`. The drawback to this, is that
it requires some maintenance to update, but allows you work around the issues from # 1
by not tracking this file in the repo.
3. `.hab.json`'s parent directory name. For distribution, this is the preferred
option. You will end up needing a version folder for each deployed version of a disto
to allow you to pick the version for a given config, so this lets you specify the
version simply by copying it to the target location.
4. `setuptools_scm.get_version` gets a version from version control. This is for
developer working copies, they can simply checkout the repo and even if its not a pip
package this will resolve a valid and automatically updated version number provided the
repo follows the setuptools_scm requirements for defining version numbers.

### Config

A config defines the environment to be applied. The context is picked by the provided URI.
They are mostly used to [define distros](#defining-distros), pin those distros
to specific versions, add [alias_mods](#alias-mods), and can be used to
[set environment variables](#defining-environments).

A given config needs two pieces of information defined, its name and context. The
context is a list of its parents names. When joined together they will build a URI.

Example project_a_thug_animation.json:
```json5
{
    "name": "Animation",
    "context": ["project_a", "Thug"],
    "alias_mods": {
         // Modify this env variable only when using the maya alias
        "maya": {
            "environment": {
                "os_specific": true,
                "windows": {"append": {"MAYA_MODULE_PATH": "//server/share/project_a"}}
            }
        }
    },
    "environment": {
        "set": {
            // Explicitly set this environment variable to a value
            "STUDIO_PROJECT": "project_a"
        }
    },
    // Inherit any configurations NotSet in this file from the parent context
    "inherits": true,
    // Require any version of the Maya2020 distro
    "distros": [
        "maya2020"
    ]
}
```

This config would have the URI `project_a/Thug/Animation`.

Configs support [min_verbosity](#min_verbosity) [with inheritance](tests/configs/verbosity).

#### Config Inheritance

When resolving a URI it will find the closest exact match, so if `project_a/Thug` is
passed but Thug does not have a config, its parent project_a is used. If there is no
config for project_a, the default config will be used.

The config system has an inheritance system that follows a tree structure. If a property
is `hab.NotSet` on the chosen config and the config has inherit enabled the closest
parent with that property set will be used. If the root of the tree has inherit
enabled, and the property still is `hab.NotSet`, then the `default` tree will be
checked.

When the default tree is checked when resolving inheritance, some special rules for
matching contexts are applied. It will attempt to find the most specific context defined
in the default tree, but it will find the largest partial match for the start of each
URI identifier. In the [default test config](tests/configs/default), you will see `Sc1`
and `Sc11`. The URI of `not_a_project/Sc101` would end up using `default/Sc1`. The URI
`not_a_project/Sc110` would use `default/Sc11`. The URI `not_a_project/Sc200` would
use `default`.

### Variable Formatting

The configuration environment variables and aliases can be formatted using str.format syntax.

Currently supported variables:
* `{relative_root}`: The directory name of the .json config file. Think of this as the relative path
`.` when using the command line, but this is a clear indication that it needs to be
replaced with the dirname and not left alone.
* `{ANYTHING!e}`: `!e` is a special conversion flag for Environment variables. This will
be replaced with the correct shell environment variable. For bash it becomes `$ANYTHING`,
in power shell `$env:ANYTHING`, and in command prompt `%ANYTHING%`. ANYTHING is the name
of the environment variable.
* `{;}`: This is replaced with the path separator for the shell. Ie `:` for bash, and `;`
on windows(including bash).

### Min_Verbosity

[Config](#config) and [aliases](#hiding-aliases) can be hidden depending on the
verbosity setting the user is using. The schema for this is:
```json
"min_verbosity": {
   "global": 1,
   "hab": 2,
   "hab-gui": 0
}
```
The `global` key is used as a default value if a more specific key is requested
and not defined. Other keys can be used for more fine grained control of that
workflow. By default the target `hab` is used. The cli uses `hab`.

Filtering is not enabled by default, code needs to opt into it by using a with context.
```
import hab

# Specify the target when creating the Resolver instance(defaults to "hab").
resolver = hab.Resolver(target="something")
cfg = resolver.resolve('verbosity/inherit')

# By default, nothing will be hidden
print("a:", cfg.aliases.keys())

# Enable filtering by using the verbosity_filter with context.
with hab.utils.verbosity_filter(resolver, 0):
    print("b:", cfg.aliases.keys())
with hab.utils.verbosity_filter(resolver, 1):
    print("c:", cfg.aliases.keys())
```
Outputs:
```
a: dict_keys(['vb_default', 'vb0', 'vb1', 'vb2', 'vb3'])
b: dict_keys(['vb_default', 'vb0'])
c: dict_keys(['vb_default', 'vb0', 'vb1'])
```

If you use the target "hab-gui" instead of "something"
```
a: dict_keys(['vb_default', 'vb0', 'vb1', 'vb2', 'vb3'])
b: dict_keys(['vb_default', 'vb3'])
c: dict_keys(['vb_default', 'vb2', 'vb3'])
```

### Defining Aliases

Aliases are used to run a program in a specific way. The hab cli creates shell
commands for each alias. Aliases are defined on distros, and per-platform.

```json
{
    "name": "aliased",
    "aliases": {
        "windows": [
            [
                "as_dict", {
                    "cmd": ["python", "{relative_root}/list_vars.py"],
                    "environment": {
                        "prepend": {
                            "ALIASED_GLOBAL_A": "Local A Prepend",
                            "ALIASED_LOCAL": "{relative_root}/test"
                        }
                    }
                }
            ],
            ["as_list", ["python", "{relative_root}/list_vars.py"]],
            ["as_str", "python"]
        ]
    },
    "environment": {
        "set": {
            "ALIASED_GLOBAL_A": "Global A"
        }
    }
}
```

This example distro shows the various ways you can define aliases. Each alias is
defined as a two part list where the first item is the name of the created alias
command. The second argument is the actual command to run and configuration
definition.

Ultimately all alias definitions are turned into dictionaries like `as_dict`, but
you can also define aliases as lists of strings or a single string. It's
recommended that you use a list of strings for any commands that require multiple
arguments, for more details see args documentation in
[subprocess.Popen](https://docs.python.org/3/library/subprocess.html#subprocess.Popen).


#### Complex Aliases

`as_list` and `as_str` show simple aliases. Ie aliases that just need to run a
command from inside the current hab environment. They inherit the environment
from the active hab config.

`as_dict` shows a complex alias, that also inherits the environment from the
active hab config, but in this case prepends an additional value on
`ALIASED_GLOBAL_A`. While this distro is in use, the environment variable
`ALIASED_GLOBAL_A` will be set to `Global A`. However while you are using the
alias `as_dict`, the variable will be set to `Local A Prepend;Global A`.

Complex Aliases supports several keys:
1. `cmd` is the command to run. When list or str defined aliases are resolved,
their value is stored under this key.
2. `environment`: A set of env var configuration options. For details on this
format, see [Defining Environments](#defining-environments). This is not
os_specific due to aliases already being defined per-platform.
3. `launch_cls`: If defined this entry_point is used instead of the Site defined
or default class specifically for launching this alias.
See [houdini](tests/distros/houdini19.5/19.5.493/.hab.json) for an example.

Note: Plugins may add support for their own keys.
[Hab-gui](https://github.com/blurstudio/hab-gui#icons-and-labels)
adds icon and label for example.

**Use Case:** You want to add a custom AssetResolver to USD for Maya, Houdini,
and standalone usdview. To get this to work, you need to compile your plugin
against each of these applications unique compiling requirements. This means that
you also need to set the env var `PXR_PLUGINPATH_NAME` to a unique path for each
application. Maya's .mod files and houdini's plugin json files make it relatively
easy for the distro to update the global env vars `MAYA_MODULE_PATH` and
`HOUDINI_PACKAGE_DIR` to application specific configs setting the env var correctly.
However, that doesn't work for the standalone usdview application which doesn't
have a robust plugin loading system that can resolve application specific dll/so
files at startup. If you were to set the `PXR_PLUGINPATH_NAME` env var globally,
it would break houdini and maya as they would try to load the standalone path.
This is where complex aliases are useful. The usd distro can define an complex
alias to launch usdview that only adds the path to your standalone plugin to
`PXR_PLUGINPATH_NAME` only when that alias is launched.

#### Alias Mods

Alias mods provide a way for a [distro](#defining-distros) or [config](#config)
to modify another distro's aliases. This is useful for plugins that need to modify
more than one host application independently.

```json
{
    "name": "aliased_mod",
    "alias_mods": {
        "as_list": {
            "environment": {
                "os_specific": true,
                "windows": {
                    "set": {
                        "ALIASED_MOD_LOCAL_B": "Local Mod B"
                    }
                }
            }
        }
    },
}
```
This example is forcing an the env var `ALIASED_MOD_LOCAL_B` to `Local Mod B` if
the resolved config has the alias `as_list`. Assuming the above aliased and this
aliased_mod distro are loaded, then the resulting `as_list` command would now set
the `ALIASED_MOD_LOCAL_B` env var to `Local Mod B` before calling its cmd.
Currently only the environment key is supported, and is os_specific.

**Use Case:** The complex alias use case has a drawback, it ties your usd version
to a specific usd plugin release. You likely will have multiple releases of your
plugin for the same usd version, as well as having multiple plugins you want to
version independently. To do this you can define a distro for each USD plugin,
and modify the `PXR_PLUGINPATH_NAME` env var for usdview using alias_mods.

#### Hiding aliases

You may find that you have to define more aliases than a regular user will
regularly need, making the dump of aliases long and hard to parse. When using
complex aliases, you can specify min_verbosity settings that will prevent showing
some of those aliases unless you enable a higher verbosity.

For example all of `site_main.json`'s aliases are:
```
maya mayapy maya20 mayapy20 pip houdini houdini18.5 houdinicore houdinicore18.5 husk husk18.5
```
While these are all useful, especially if you want to include access to
[Multiple versions](#multiple-app-versions) of maya or houdini, but in most cases
your users should only call `maya` or `houdini`, and don't need to call the script
aliases like mayapy, husk etc.

Using [min_verbosity](#min_verbosity), you can make it so you have to increase the
verbosity of dump's to see these advanced aliases. See [](tests/distros/maya/2020.1/.hab.json).

By default just show the non-versioned aliases
```
$ hab dump default
Dump of FlatConfig('default')
-------------------------------------------
aliases:  maya houdini houdinicore
-------------------------------------------
```
Adding a verbosity level now shows the version aliases as well
```
$ hab dump default -v
Dump of FlatConfig('default')
--------------------------------------------------------------------------
name:  default
uri:  default
aliases:  maya maya20 houdini houdini18.5 houdinicore houdinicore18.5 husk
          husk18.5
```
Adding another verbosity level now shows advanced aliases like mayapy and husk.
```
$ hab dump default -vv
Dump of FlatConfig('default')
-------------------------------------------------------------------------
name:  default
uri:  default
aliases:  maya mayapy maya20 mayapy20 pip houdini houdini18.5 houdinicore
          houdinicore18.5 husk husk18.5
```

### Defining Environments

The `environment` key in distro and config definitions is used to configure modifications
to the resolved environment. This is stored in `HabBase.environment_config`.

```json
    "environment": {
        "unset": [
            "UNSET_VARIABLE"
        ],
        "set": {
            "MAYA_MODULE_PATH": "{relative_root}"
        },
        "append": {
            "MAYA_MODULE_PATH": "{relative_root}/append",
        },
        "prepend": {
            "MAYA_MODULE_PATH": "prepend_value"
        }
    }
```

There are 4 valid top level keys they are processed in this order if used:
* unset: The names of environment variables to remove.
* set: Replace or set the environment variable to this value.
* prepend: Treat this variable as a list and insert the value at the start of the list.
* append: Treat this variable as a list and add the value at the end of the list.

The `unset` key stores a list of environment variable names, the rest store a dictionary
of environment variable keys and the values to store.

The `HabBase.environment` property shows the final resolved
environment variables that will be applied. When using a resolved `FlatConfig` object,
environment also contains the merger of all environment_config definitions for all
`distros`. When building append and prepend environment variables it processes
each dependency in a depth-first manner.

These environment variables will be directly set if there is a value, and unset if the
value is blank. Hab doesn't inherit the session/system/user environment variable
values with the exception of the `PATH` variable as this would break the system.
Like Rez, the first set, prepend or append operation on a variable will replace the
existing variable value.

This quote from the Rez documentation explains why:
> "Why does this happen? Consider PYTHONPATH - if an initial overwrite did not happen,
> then any modules visible on PYTHONPATH before the rez environment was configured would
> still be there. This would mean you may not have a properly configured environment. If
> your system PyQt were on PYTHONPATH for example, and you used rez-env to set a
> different PyQt version, an attempt to import it within the configured environment would
> still, incorrectly, import the system version."

If required, you can create OS specific environment variable definitions. To do this,
you nest the above structure into a dictionary with the correct `windows` or `linux`
key. You have to add a extra key `os_specific` set to `true` to indicate that you are
using os specific configurations.

```json
    "environment": {
        "os_specific": true,
        "windows": {
            "append": {
                "GOLAEM_WINDOWS_PATH": "C:\\Golaem\\Golaem-7.3.11\\Maya2020"
            }
        },
        "linux": {
            "append": {
                "GOLAEM_LINUX_PATH": "/Golaem/Golaem-7.3.11/Maya2020"
            }
        }
    }
```


### Defining Distros

The `distos` key in distro and config definitions are used to define the distro version
requirements. When a config is processed the distro requirements are evaluated recursively
to include the requirements of the latest DistroVersion matching the specifier.
This uses the python [packaging module](https://packaging.pypa.io/en/stable/requirements.html)
to resolve version specifiers so you can use the same configuration syntax you
would use in a pip requirements file.

```json5
    "distros": [
        "maya2020",
        "maya2022",
        "houdini18.5",
        "hsite",
        "animBot<=1.4",
        "studiolibrary==2.5.7.post1",
        // Use markers to only include 3ds max if hab is currently running on
        // windows. It can't be run on linux.
        "3dsmax2019;platform_system=='Windows'"
    ]
```

The resolved versions matching the requested distros are shown in the `versions` property.

It also supports [markers](https://packaging.pypa.io/en/stable/markers.html). Hab
should support all of the [officially supported markers](https://peps.python.org/pep-0508/),
but the most common marker likely to be used with hab is `platform_system`.

### Platform specific code

Hab works on windows, linux and osx(needs tested). To make it easier to handle
platform specific code, it has all been moved into ``hab.utils.Platform`` instead
of directly relying on ``sys.platform``, ``os.path``, etc. This also has the
benefit of making it so the testing suite can test that hab works on for all
platforms without needing to test your code individually on each platform.
Ultimately we still need to test hab on each platform individually, but this
should help reduce surprises when the CI/CD runs the tests on a platform you
don't have easy access to when developing.

Hab can be forced to simulate being run on a different platform by replacing
the Platform object.

```py
hab.utils.Platform = hab.utils.WinPlatform
hab.utils.Platform = utils.BasePlatform.get_platform('osx')
# Restore the current platform
hab.utils.Platform = BasePlatform.get_platform()
```

When working with tests, its recommended that you use the monkeypatch fixture.

```py
monkeypatch.setattr(utils, "Platform", utils.LinuxPlatform)
monkeypatch.setattr(utils, "Platform", utils.WinPlatform)
```

# Debugging

## Debugging generated scripts

Hab doesn't use a console_script entry point to create an exe for its cli. It uses a shell
specific [launch script](bin). This script runs hab as a python process to create
temporary shell scripts to configure the shell(launching a new one if required).
This prevents the need to keep the python process running and prevents shell
corruption if that python process is killed. The shell scripts are written to the
temp location for the shell/os. On windows this should be written to `%tmp%` and
`$TMPDIR` on linux.

Hab does its best to remove these temp script files on exit so inspecting them can be
difficult. The best way to view them is to run a `hab env` or `hab launch` command
this will leave the hab process running while you find and view the config and launch
scripts in the temp directory. Once you are finished exit the hab process and they
will be removed. Alternatively if you use the `--dump-scripts` flag on hab commands
that write scripts, to make it print the contents of every file to the shell
instead of writing them to disk.

# Caveats

* Using `hab activate` in the command prompt is disabled. Batch doesn't have a function
feature like the other shells, so each alias is its own .bat file in a directory
prepended to the PATH environment variable. Hab needs to clean up its temp scripts
and due to how activate works, there isn't currently a method to do this. We don't
use doskey so we can support complex aliases.
* Powershell disables running .ps1 scripts disabled by default. If you get a error like
`hab.ps1 cannot be loaded because running scripts is disabled on this system.`, you will
need to launch the Powershell with this command `powershell -ExecutionPolicy Unrestricted`.
You can administratively default the execution policy to unrestricted for windows.
* To use `hab activate` in bash or Powershell you need to use `.` or `source`. Powershell
has the `.` operator so I would use that for both Powershell and bash.
`. hab activate default`.
* Jinja2 and MarkupSafe minimum requirements should be respected. This allows hab
to work with Houdini 19.5 that ships with very dated versions of these packages.
In practice this just means that we have to cast pathlib objects to strings before
passing them to Jinja2.

# Glosary

* **activate:** Update the current process(shell) for a given configuration. Name taken
from virtualenv.
* **env:** In the cli this launches a new process for a given configuration. Name taken
from rez.
* **config:** Defines the environment variables and distros that should be used when a
specific URI is requested.
* **distro:** Defines environment variables and aliases that a specific application or
plugin requires, and other distros that it depends on.
* **site:** Apply specific settings to hab. Where to find distros and configs, etc.
* **URI:** A `/` separated list of identifiers used to choose a specific config.

# Future Plans

* Support per-alias environment variable manipulation. This will allow us to prepend to
PATH if required per-dcc. Ie only add `C:\Program Files\Chaos Group\V-Ray\3ds Max 2019\bin`
to PATH, if and only if using launching 3ds Max any time its included in the distros.
* Add support for `~` and using environment variables in config and distro path resolution.
* Add pkg_resource plugin interfaces that will allow customization. For example, how
configurations are defined. Allowing the use of site specific database integrations etc.
