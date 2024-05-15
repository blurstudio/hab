""" Enables support for calling the hab cli using `python -m hab`
"""


import sys

import hab.cli

if __name__ == "__main__":
    # prog_name prevents __main__.py from being shown as the command name in the help
    # text. We don't know the exact command the user passed so we provide a generic
    # `python -m hab` command.
    sys.exit(hab.cli.cli(prog_name="hab"))
