# Hab

A launcher that lets you configure software distributions and how they are consumed with
dependency resolution. It provides a habitat for you to work in.

Features:

* [URI](#uri) based configuration resolution with inheritance. Makes it easy to define
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

## URI

`identifier1/identifier2/...`

You specify a configuration using a simple URI of identifiers separated by a `/`.
Currently hab only supports absolute uri's.

Examples:
* projectDummy/Sc001/S0001.00
* projectDummy/Sc001/S0001.00/Animation
* projectDummy/Thug
* default

If the provided uri has no configurations provided, the default configuration is used.
This also supports inheritance with some special rules, see
[config inheritance](#config-inheritance) for more details.

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

Examples:

```bash
$ hab env projectDummy
$ hab env projectDummy/Thug
```

The cli prompt is updated while inside a hab config is active. It is `[URI] [cwd]`
Where URI is the uri requested and cwd is the current working directory.

## API

TODO

## Configuration

Hab is configured by json files found with glob strings passed to the cli or defined
by an environment variable.

### Site

Hab uses the `HAB_PATH` environment variable to point to one or more site
configuration files. If the `--site` option is passed to the cli, it is used instead of
the environment variable.

Each of the file paths specified are read and merged into a single site configuration
dictionary hab uses. The values in each file are merged so the value defined in the
right most path any given configuration option being used. See
[Defining Environments](#defining-environments) for how to structure the json to
prepend, append, set, unset values.

Developers can use this to load local site configurations loading their wip code
instead of the official releases. See the [test_resolve_paths](tests/test_site.py) to
see an example of [overriding](tests/site_override.json) the
[main](tests/site_main.json) site settings.

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

* `config_paths`: Configures where URI configs are discovered. See below.
* `distro_paths`: Configures where distros discovered. See below.
* `prereleases`: If pre-release distros should be allowed. Works the same as
`pip install --pre ...`.
* `colorize`: If `hab dump` should colorize its output for ease of reading.

`config_paths` and `distro_paths` take one or more glob paths separated by `os.pathsep`.
The paths are processed left to right. For a given glob string in these variables you
can not have duplicate values. For configs a duplicate is two configs with the same URI.
A duplicate distro is two distros with the same name and version. If this happens a
`DuplicateJsonError` is raised. This prevents developers from copying a config and
forgetting to update its context.

You can however have duplicates across individual glob paths. The glob paths are processed
left to right and the first config/distro is used, any subsequent duplicates are ignored
and a warning is logged to aid in debugging. This feature allows a developer to add any
git checkouts they are working on that will be used, but still have access to all of the
global shared configs/distros they are not working on.
See [specifying distro version](#specifying-distro-version) for details on specifying a
distro version in a git repo.

### Distro

A distro defines a application, distribution or plugin that has multiple versions. It
is mostly used to define aliases and environment variables. It can also define
additional requirements.

A recommended released distro folder structure: `[name]\[version]\.hab.json`.
The `[name]` folder is referenced by one of the disto_path globs. This makes it easy
to store multiple versions of the distro. Each glob specified by `HAB_DISTRO_PATHS` will
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

You will note that I'm using the version of maya in the name. This allows you to provide
access to multiple versions of the Maya application. Only one version of a given distro
name is going to be used so if you need access to multiple versions of maya you must use
this method. If there are duplicate alias names, only one will be provided and it is not
consistent, so you should define version specific aliases as well if you plan to use
more than one for a given config.

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
They are mostly used to define distros, lock those distros to specific versions, and can
be used to set environment variables.

A given config needs two pieces of information defined, its name and context. The
context is a list of its parents names. When joined together they would build a URI.

Example project_a_thug_animation.json:
```json
{
    "name": "Animation",
    "context": ["project_a", "Thug"],
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

#### Config Inheritance

When resolving a URI it will find the closest exact match, so if `project_a/Thug` is
passed but Thug does not have a config, its parent project_a is used. If there is no
config for project_a, the default config will be used.

The config system has an inheritance system that follows a tree structure. If a property
is `NotSet` on the chosen config and the config has inherit enabled the closest parent
with that property set will be used. If the root of the tree has inherit enabled, and
the property still is `NotSet`, then the `default` tree will be checked.

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

### Defining Aliases

Aliases are normally defined for distros. They provide information to create a command
in the terminal and what program that command runs. The top level dictionary is specifies
the operating system this alias is for. Each alias is defined as a two part list where
the first item is the name of the created alias command. The second argument is a string
or list of strings of the actual command to run. If you need to pass hard coded
arguments to the alias command you should use a list.

```json
    "aliases": {
        "windows": [
            ["hython", "C:/Program Files/Side Effects Software/Houdini 19.0.578/bin/hython.exe"],
            [
                "usdview",
                [
                    "C:/Program Files/Side Effects Software/Houdini 19.0.578/bin/hython",
                    "C:/Program Files/Side Effects Software/Houdini 19.0.578/bin/usdview"
                ]
            ],
        ],
        "linux": [
            ["hython", "/opt/hfs19.0.578/bin/hython"]
        ]
    }
```

`HabBase.aliases` is reduced to just the current operating system's aliases. Ie if
this is run on windows, you would have access to both the hython and usdview alias, but
on linux you would only have access to hython.


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
`distros`.
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

The `distos` key in distro and config definitions is used to define the distro version
requirements. When a config is processed the distro requirements are evaluated recursively
to include the requirements of the latest DistroVersion matching the specifier.
This uses the python packaging module to resolve version specifiers so you can use the
same configuration syntax you would use in a pip requirements file.

```json
    "distros": [
        "maya2020",
        "maya2022",
        "houdini18.5",
        "hsite",
        "animBot<=1.4",
        "studiolibrary==2.5.7.post1"
    ]

```

The resolved versions matching the requested distros are shown in the `versions` property.


# Caveats

* When using `hab env` in the command prompt, doskey aliases don't get cleared when you
exit a context.
* Powershell disables running .ps1 scripts disabled by default. If you get a error like
`hab.ps1 cannot be loaded because running scripts is disabled on this system.`, you will
need to launch the Powershell with this command `powershell -ExecutionPolicy Unrestricted`.
You can administratively default the execution policy to unrestricted for windows.
* To use `hab activate` in bash or Powershell you need to use `.` or `source`. Powershell
has the `.` operator so I would use that for both Powershell and bash.
`. hab activate default`.

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
