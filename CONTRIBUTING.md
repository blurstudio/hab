# Contributing to Blur Projects

We at Blur are excited to contribute to the Visual Effects community by open sourcing our internal projects. We welcome others to integrate these projects into their pipelines and contribute to them as they deem fit via bug reports, feature suggestions, and pull requests.

<!-- MarkdownTOC -->

- [Code of Conduct](#code-of-conduct)
- [How to Contribute](#how-to-contribute)
    - [Reporting Issues / Bugs](#reporting-issues--bugs)
    - [Suggesting a Feature](#suggesting-a-feature)
    - [Submitting a Pull Request](#submitting-a-pull-request)
- [Coding Style & Formatting](#coding-style--formatting)
- [Creating a Release](#creating-a-release)

<!-- /MarkdownTOC -->

## Code of Conduct

Before contributing we recommend checking out our _[code of conduct]_. Thanks! :smile:

## How to Contribute

### Reporting Issues / Bugs

- Double check that the bug has not already been reported by searching the project's GitHub [Issues].
    - If an issue already exists, you're welcome to add additional context that may not already be present in the original message via the comments.
- Once you have verified no pre-existing bug report exists, [create a new issue].
    - Provide a title and concise description.
    - Include as much detailed information regarding the problem as possible.
    - Supply reproducible steps that demonstrate the behavior.

### Suggesting a Feature

- Double check that a similar request has not already been made by searching the project's GitHub [Issues].
- If no issue exists pertaining to your feature request, [create a new issue].
    - Provide a title and concise description.
    - Describe what functionality is missing and why it would be useful for yourself and others.
    - If relevant, include any screenshots, animated GIFs, or sketches that might further demonstrate the desired feature.

### Submitting a Pull Request

1. Fork the Project
2. Create your Branch (`git checkout -b my-amazing-feature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
    - Be sure to follow our coding style and formatting conventions (below).
4. Push to the Branch (`git push origin my-amazing-feature`)
5. Open a Pull Request
    - List what you've done.
    - Link to any related or addressed issues or feature requests.

## Coding Style & Formatting

In order to streamline reviews and reduce the barrier-to-entry for developers, we've adopted several standardized tools and workflows to maintain a consistent and reliable code appearance.

A set of GitHub Action workflows are in place to perform the following style and formatting checks against every push to our project repositories. These checks must successfully pass before a pull request can be accepted.

**Styling**

Styling or linting is performed via [flake8] along with the plugins [flake8-bugbear] & [pep8-naming]. A minor amount of configuration has been added to _[setup.cfg]_ in order to provide better compatibility with our formatter black (see next section).

**Formatting**

Code formatting is completed by [black]. By relinquishing code appearance standards to Black we manage to greatly reduce semantic arguments/discussions that might distract from progress on a project.


## Creating a Release

Releases are made manually by project managers and will automatically be uploaded to PyPI (via GitHib Action workflow) once completed.

[flake8]: https://github.com/PyCQA/flake8
[flake8-bugbear]: https://github.com/PyCQA/flake8-bugbear
[pep8-naming]: https://github.com/PyCQA/pep8-naming
[setup.cfg]: https://github.com/blurstudio/python-example/blob/master/setup.cfg
[black]: https://github.com/psf/black
[Issues]: https://github.com/blurstudio/python-example/issues
[create a new issue]: https://github.com/blurstudio/python-example/issues/new
[code of conduct]: https://github.com/blurstudio/python-example/blob/master/CODE_OF_CONDUCT.md
