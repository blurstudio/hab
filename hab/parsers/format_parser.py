from colorama import Fore


class FormatParser:
    """Used to format HabBase objects into a readable string.

    Parameters:
        top_level (str): Formatting applied to name if this is a top level item.
            This is applied to the name value before passed to simple/verbose.
        simple (str): A str.format string used to generate the non-verbose output.
        verbose (str): A str.format string used to generate the verbose output.

    All of the format strings are provided the kwargs `pre`, `name` and `filename`

    Args:
        verbosity (int): Controls the complexity of the output. If zero then
            `self.simple` is used, otherwise `self.verbose` is uses.
        color (bool, optional): Enables adding color control characters for readability.
    """

    def __init__(self, verbosity, color=True):
        self.color = color
        self.verbosity = verbosity

        # Configure the format strings
        self.simple = "{pre}{name}"
        if self.color:
            self.verbose = f'{{pre}}{{name}}: {Fore.YELLOW}"{{filename}}"{Fore.RESET}'
            self.top_level = f"{Fore.GREEN}{{name}}{Fore.RESET}"
        else:
            self.verbose = '{pre}{name}: "{filename}"'
            self.top_level = "{name}"

    def format(self, parser, attr, pre):
        """Format the output of Config or Distro for printing based on verbosity."""
        name = getattr(parser, attr)
        if not pre:
            name = self.top_level.format(pre=pre, name=name, filename=parser.filename)

        if not self.verbosity or not parser.filename:
            fmt = self.simple
        else:
            fmt = self.verbose
        return fmt.format(pre=pre, name=name, filename=parser.filename)
