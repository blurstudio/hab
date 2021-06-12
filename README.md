# Python Example

This is a template project to jump-start the creation of additional project repositories, managed by Blur Studio, on GitHub. Below is a walk-through of various characteristics of the project.

## Package Configuration

### `setup.py`

- Enables the `setuptools` extension `setuptools_scm`. This extension replaces the need to statically define a package's version and instead derives the version from SCM metadata (such as the latest git tag).
- Permit package installation in editable mode. (i.e. `pip install -e .`)

_You should not need to modify the contents `setup.py`._

> _Originally `setup.py` was the primary manor by which to define a package's metadata. It has mostly been replaced by `setup.cfg`._

### `setup.cfg`

- Defines static package metadata such as package description, author, and PyPI classifiers.
- Lists package requirements (`install_requires`).
- Lists auxiliary package requirements (`extras_require`). These can be installed by appending the extras group name (or "all" for all groups) in square-brackets upon install (ex: `pip install -e .[lint]`).
- Configures `flake8`.

_Be sure to update the various properties so they pertain to your project._

### `pyproject.toml`

- Defines build system characteristics, more specifically those pertaining to `setuptools_scm` which provides automatic versioning based off git repo state.
- Configures `pytest`.

_The only property that will need updating is the `write_to` destination for the `version.txt`-file._

> _While it would be ideal to fully migrate to `pyproject.toml` there are still several aspects of configuration that have not yet fully migrated to support the finalized [PEP 621] standard._

### `requirements.txt` & `requirements-dev.txt`

- Defines a list of packages required in order to install and run the project's package.
- The `-dev` requirements file lists packages useful during development (ex: `pytest`, `flake8`).

_Keep these up to date with any packages required by the project._

## Coding Style & Formatting

### flake8

Analyses for a number of common errors and syntactical violations. Configuration is provided by a section in `setup.cfg`.

### black

Conforms code to a set of opinionated formatting standards.

## Pre-commit Hooks

To simplify the linting and formatting process a basic configuration of pre-commit has been added. Integrating with Git hooks, pre-commit executes a set of actions before a commit is added to the repository interrupting the commit if any of the hooks fail or make additional changes.

Before you can start using pre-commit you will need to install it via pip (`pip install pre-commit`) and install the Git hook scripts into your local copy of the Git repository (`pre-commit install`). The next time any changes are committed those scripts will execute and run the hooks configured in `.pre-commit-config.yaml`. Below are the hooks currently configured:

| Hook                     | Description                                                        |
|--------------------------|--------------------------------------------------------------------|
| [black]                  | Conforms code to a set of opinionated formatting standards.        |
| [flake8]                 | Analyses for a number of common errors and syntactical violations. |
| [setup-cfg-fmt]          | Applies a consistent format to `setup.cfg` files.                  |
| [check-json]             | Attempts to load all json files to verify syntax.                  |
| [check-toml]             | Attempts to load all toml files to verify syntax.                  |
| [check-xml]              | Attempts to load all xml files to verify syntax.                   |
| [check-yaml]             | Attempts to load all yaml files to verify syntax.                  |
| [debug-statements]       | Ensures there are no debug breakpoints present.                    |
| [end-of-file-fixer]      | Ensures each file has one newline at the end.                      |
| [requirements-txt-fixer] | Sorts entries in requirements.txt and removes incorrect entries.   |
| [trailing-whitespace]    | Trims any trailing whitespace from lines.                          |

## GitHub Action Workflows

### Static Analysis

Runs against every push, regardless of branch. Checks the codebase for common errors and syntactical violations with `flake8` and that the code is formatted according to `black`.

### Release

Runs when a new release is created.

## Community Documents

### `CODE_OF_CONDUCT.md`

Describes a set of standards contributors and maintainers alike are intended to follow when interacting with and contributing to projects maintained by Blur Studio.

### `CONTRIBUTING.md`

A kick-start document standardizing the manor by which other developers can contribute to projects maintained by Blur Studio.

### `BUG_REPORT.md`, `FEATURE_REQUEST.md`, & `PULL_REQUEST_TEMPLATE.md`

Templates for reporting issues (bugs or feature requests) and submitting pull requests. Each provide a scaffolding for reporters and contributors to follow, ensuring each request has the appropriate information upon first submission.

[PEP 621]: https://www.python.org/dev/peps/pep-0621/
[black]: https://github.com/psf/black
[flake8]: https://gitlab.com/pycqa/flake8
[setup-cfg-fmt]: https://github.com/asottile/setup-cfg-fmt
[check-json]: https://github.com/pre-commit/pre-commit-hooks#check-json
[check-toml]: https://github.com/pre-commit/pre-commit-hooks#check-toml
[check-xml]: https://github.com/pre-commit/pre-commit-hooks#check-xml
[check-yaml]: https://github.com/pre-commit/pre-commit-hooks#check-yaml
[debug-statements]: https://github.com/pre-commit/pre-commit-hooks#debug-statements
[end-of-file-fixer]: https://github.com/pre-commit/pre-commit-hooks#end-of-file-fixer
[requirements-txt-fixer]: https://github.com/pre-commit/pre-commit-hooks#requirements-txt-fixer
[trailing-whitespace]: https://github.com/pre-commit/pre-commit-hooks#trailing-whitespace
