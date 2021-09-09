# Habitat

A launcher that lets you configure software distributions and how they are consumed with
dependency resolution.

## URI

`identifier1/identifier2/...`

You specify a configuration using a simple URI of identifiers separated by a `/`.
Currently habitat only supports absolute uri's. We are working on developing a more
feature rich uri for Trax and we will add support for that in habitat.

Examples:
* projectDummy/Sc001/S0001.00
* projectDummy/Sc001/S0001.00/Animation
* projectDummy/Thug
* default

## CLI

The Habitat cli is the current way that users will interact with habitat, but all of the
actual work is done in the api so we can make gui's based on habitat in the future.

1. `hab env`: The env command launches a new shell configured by habitat. You can exit
the shell to return to the original configuration. This is how most users will interact
with habitat in the command line.
2. `hab activate`: Updates the current shell with the habitat configuration. This is
similar to activating a virtualenv, but currently there is no way to deactivate. This is
 mostly how scripts can make use of habitat.
 3. `hab dump`: Formats the resolved configuration and prints it. Used for debugging
 configurations.

Examples:

```bash
$ hab env projectDummy
$ hab env projectDummy/Thug
```

The cli prompt is updated while inside a habitat config is active. It is `[URI] [cwd]`
Where URI is the uri requested and cwd is the current working directory.

## API

TODO

## Configuration

Habitat is configured by json files found with glob strings passed to the cli or defined
by environment variables.

### Habitat env variables

Habitat uses two environment variables to configure how it finds distro and config files.

* `HAB_CONFIG_PATHS`: Configures where configs are discovered.
* `HAB_DISTRO_PATHS`: Configures where distros discovered.

These variables take one or more glob paths separated by `os.pathsep`. The paths are
processed left to right. For a given glob string in these variables you can not have
duplicate values. For configs a duplicate is two configs with the same URI. A duplicate
distro is two distros with the same name and version. If this happens a
`DuplicateJsonError` is raised. This prevents developers from copying a config and
forgetting to update its context.

You can however have duplicates across individual glob paths. The glob paths are processed
left to right and the first config/distro is used, any subsequent duplicates are ignored
and a warning is logged to aid in debugging. This feature allows a developer to add any
git checkouts they are working on that will be used, but still have access to all of the
global shared configs/distros they are not working on.
See [specifying distro version](#Specifying-distro-version) for details on specifying a
distro version in a git repo.

* `HAB_CONFIG_PATHS` example: `~/development/configs:/mnt/studio/configs/*`
* `HAB_DISTRO_PATHS` example: `~/development/distros:/mnt/studio/distros/*/*`

### Distro

A distro defines a application or plugin that has multiple versions. It is mostly used
to define aliases and environment variables. It can also define additional requirements.

A recommended released distro folder structure: `[name]\[version]\.habitat.json`.
The `[name]` folder is referenced by one of the disto_path globs. This makes it easy
to store multiple versions of the distro. Each glob specified by `HAB_DISTRO_PATHS` will
automatically have `/*/.habitat.json` added to it, so the `.habitat.json` file should
be in the root of a version folder. The root of the version folder is likely the root of
a git repo.

Example .habitat.json:
```json
{
    "name": "maya2020",
    "version": "2020.1",
    "environment": {
        "append": {
            "MAYA_MODULE_PATH": "{dot}"
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

In most cases  you will not define version in `.habitat.json`. If not defined, the
parent folder is used as the version. This makes it easy for automated deployments
without needing to modify a file checked into version control.

You will note that I'm using the version of maya in the name. This allows you to provide
access to multiple versions of the Maya application. Only one version of a given distro
name is going to be used so if you need access to multiple versions of maya you must use
this method. If there are duplicate alias names, only one will be provided and it is not
consistent, so you should define version specific aliases as well if you pan to use more
than one for a given config.

#### Specifying distro version

There are a few ways to define a distro version, they are provided to make deployment
and development testing easy. Here is the 4 ways to define the version of a distro, the
first one found is used.

1. The version property in `.habitat.json`. This has some drawbacks, `.habitat.json` is
likely checked into version control so modifying this requires committing changes to
the repo, or working copy changes you have to maintain.
2. A `.habitat_version.txt` file next to `.habitat.json`. The drawback to this, is that
it requires some maintenance to update, but allows you work around the issues from # 1
by not tracking this file in the repo.
3. `.habitat.json`'s parent directory name. For distribution, this is the preferred
option. You will end up needing a version folder for each deployed version of a disto
to allow you to pick the version for a given config, so this lets you specify the
version simply by copying it to the target location.
4. `setuptools_scm.get_version` gets a version from version control. This is for
developer working copies, they can simply checkout the repo and even if its not a pip
package this will resolve a valid and automatically updated version number provided the
repo follows the setuptools_scm requirements for defining version numbers.

### Config

A config defines the environment to be applied. The context is picked by the provided URI.
This is where we will define project/asset/sequence/department etc specific configurations.
They are mostly used to define distros, lock those distros to specific versions, and can
be used to set environment variables like `BDEV_TOOL_ENVIRONMENT` to force users to a
specific treegrunt environment.

A given config needs two pieces of information defined, its name and context. The
context is a list of its parents names. When joined together they would build a URI.

Example project_a_thug_animation.json:
```json
{
    "name": "Animation",
    "context": ["project_a", "Thug"],
    "environment": {
        "set": {
            "BDEV_TOOL_ENVIRONMENT": "project_a"
        }
    },
    "inherits": true,
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
in the default tree, but it will find the largest partial match for the start each URI
identifier. In the [default test config](tests/configs/default), you will see `Sc1` and
`Sc11`. The URI of `not_a_project/Sc101` would end up using `default/Sc1`. The URI
`not_a_project/Sc110` would use `default/Sc11`. The URI `not_a_project/Sc200` would
use `default`.

### Variable Formatting

The configuration environment variables and aliases can be formatted using str.format syntax.

Currently supported variables:
* `{dot}`: The directory name of the .json config file. Think of this as the relative path
`.` when using the command line, but this is a clear indication that it needs to be
replaced with the dirname and not left alone.

### Defining Aliases

Aliases are normally defined for distros. They provide information to create a command
in the terminal and what program that command runs. The top level dictionary is specifies
the operating system this alias is for.

```json
    "aliases": {
        "windows": [
            ["maya", "C:\\Program Files\\Autodesk\\Maya2022\\bin\\maya.exe"],
            ["mayapy", "C:\\Program Files\\Autodesk\\Maya2022\\bin\\mayapy.exe"]
        ],
        "linux": [
            ["maya", "/usr/autodesk/maya2022/bin/maya2022"],
            ["mayapy", "/usr/autodesk/maya2022/bin/mayapy"]
        ]
    }
```

`HabitatBase.aliases` is reduced to just the current operating system's aliases.


### Defining Environments

The `environment` key in distro and config definitions is used to configure modifications
to the resolved environment. This is stored in `HabitatBase.environment_config`.

```json
    "environment": {
        "unset": [
            "UNSET_VARIABLE"
        ], 
        "set": {
            "MAYA_MODULE_PATH": "{dot}"
        }, 
        "append": {
            "MAYA_MODULE_PATH": "{dot}/append",
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

The `HabitatBase.environment` property shows the final resolved
environment variables that will be applied. When using a resolved `FlatConfig` object,
environment also contains the merger of all environment_config definitions for all
`distros`.
These environment variables will be directly set if there is a value, and unset if the
value is blank. Habitat doesn't inherit the session/system/user environment variable
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
to include the requirements of the latest ApplicationVersion matching the specifier.
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
We can administratively default the execution policy to unrestricted, so we may do that
in the future.
* To use `hab activate` in bash or Powershell you need to use `source`. Powershell has the
`.` operator so I would use that for both Powershell and bash. `. hab activate default`.

# Glosary

* activate: Update the current process(shell) for a given configuration. Name taken from virtualenv.
* env: In the cli this launches a new process for a given configuration. Name taken from rez.
* config: Defines the environment variables and distros that should be used when a
specific URI is requested.
* distro: Defines environment variables and aliases that a specific application or
plugin requires, and other distros that it depends on.
* URI: A `/` separated list of identifiers used to choose a specific config.

# Future Plans

* Support per-alias environment variable manipulation. This will allow us to prepend to
PATH if required per-dcc. Ie only add `C:\Program Files\Chaos Group\V-Ray\3ds Max 2019\bin`
to PATH, if and only if using launching 3ds Max.
* I need to add support for `~` and using environment variables for the
`HAB_DISTRO_PATHS` and `HAB_CONFIG_PATHS`.
* I plan to setup pkg_resource plugin interfaces that will allow us to customize how
configurations are defined. This will allow us to define the configurations using the
database not json files on the network. But we can still use json files to define
offsite/offline workflows.
* I'm thinking of making it so a config can define overrides for distro requirements.
* Update the HabitatBase.dump to show the nice requires list for distros. They show the
same info, but requires is readable and distros is not. The api needs the contents of
distros. They show the same info so its not worth showing both of them.


# Terms

This is a list of most of the names of objects and a really quick description of what
they are used for. I think we should come up with better names for a lot of this stuff,
so suggestions are welcome.

* **Resolver:** The main class of habitat(probably needs renamed)
* **Resolver.config:** What a user chooses to load. Normally defined by a URI like `project_a/Sc001/S0001.00/Animation`.
* **Resolver.distro:** Defines a version of a DCC or plugin. Config's specify distros that are required.
* **Resolver.closest_config:** Resolves the requested URI into the closest defined config. The closest_config for `project_a/Sc001/S0001.00/Animation` may resolve to `project_a/Sc001`, or even `default`, etc.
* **Resolver.dump_forest and HabitatBase.dump:** are methods to print readable representations of the object for debugging.
* **Resolver.resolve:** Uses Resolver.closest_config then converts that into a FlatConfig with reduced.
* **habitat.parsers.NotSet:** A None like object used to indicate that a parser property was not modified by any configuration. This is important for resolving the FlatConfig object.
* **HabitatProperty:** A subclass of property that lets the HabitatMeta metaclass populate the _properties set with all HabitatProperty names.
* **forest:** A dictionary map of Configs or Distros. These are stored on Resolver._configs and Resolver._distros.
* **HabitatBase.context:** The resolved URI parents of the current HabitatBase object. This does not include the name of the object, just its parents. `project_a/Sc001` would resolve into context: `["project_a"]` and name: `"Sc001"`.
* **HabitatBase.distros:** A map of `packaging.requirements.Requirement` objects defining what distros to load
* **HabitatBase.environment:** The final resolved set of environment variables that this config should load or application should add to the config.
* **HabitatBase.environment_config:** A dict of instructions for how to build environment variables. If a value should be prepended or appended or set. environment is build from these sets of instructions.
* **HabitatBase.format_environment_value:** Uses str.format with a built set of kwargs to fill in. For example, replaces {dot} with HabitatBase.dirname replicating `.` in file paths. Also used on aliases.
* **HabitatBase.name:** The name of the config or distro.
* **HabitatBase.reduced:** Turns a Config instance into a FlatConfig that is fully resolved including any inherited values from higher in the config.
* **HabitatBase.requires:** A simple string list of the resolved requirements this config requires.
* **HabitatBase.uri:** The URI a config is for.
* **HabitatBase.write_script:** Writes a config and optionally a launcher script to configure a terminal to match the resolved configuration.
* **HabitatBase.alias:** The name of a alias to create in the terminal and the command to associate with the terminal.
* **Application: Subclass of HabitatBase:** The container for ApplicationVersion objects. One per DCC or plugin exists in the distro forest. This probably should be renamed to Distro.
* **ApplicationVersion: Subclass of HabitatBase:** A specific version of the given application, its requirements, aliases, and environment variables. This probably should be renamed to DistroVersion.
* **Config: Subclass of HabitatBase:** All configs are resolved into these objects. The configuration for a given URI that defines what environment variables and Applications need to be loaded if this config is chosen.
* **FlatConfig: Subclass of Config:** A fully resolved and flattened Config object. Any values NotSet on the Config this is built from, are attempted to be set from the parents of that Config. If still not found, it will attempt to find the value from a matching config on the Default tree instead.
* **Placeholder: Subclass of HabitatBase:** Used as the parent of a config if no parent config was found.
* **hab env:** Creates a new terminal in an existing terminal with all environment variables, aliases and the prompt configured. You can exit the terminal to get back to the previous settings.
* **hab activate:** Updates the current terminal in the same way as cli.env. Mostly intended for scripts. You can not exit the terminal to get back to your old terminal.
* **hab dump:** Prints the results of dump and dump_forest for debugging and inspection.
* **Solver:** A class used to solve the recursive dependency to a flat list that matches all requirements.
