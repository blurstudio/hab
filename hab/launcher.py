import subprocess
import sys

from . import utils

try:
    CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW
except AttributeError:
    # This constant comes from the WindowsAPI, but is not
    # defined in subprocess until python 3.7
    CREATE_NO_WINDOW = 0x08000000


class Launcher(subprocess.Popen):
    """Runs cmd using subprocess.Popen enabling stdout/err/in redirection.
    On windows prevents showing of command prompts when running with pythonw.

    Args:
        args (list or string): The command to be run by subprocess.
        **kwargs: Any keyword arguments are passed to subprocess.Popen. The
            standard defaults for **kwargs are modified to enable stdout/stderr
            capture to a single merged stdout stream. Also adds platform specific
            workarounds for stdin. Changes bufsize to 1 if possible to allow for
            per-line updating of output.
    """

    def __init__(self, args, **kwargs):
        # Change the defaults for subprocess.Popen to make it easier to capture
        # output from the launched subprocess.
        kwargs.setdefault("stdout", subprocess.PIPE)
        kwargs.setdefault("stderr", subprocess.STDOUT)
        kwargs.setdefault("universal_newlines", True)
        # In python 3.8+ changing bufsize when universal_newlines is False
        # causes a warning message.
        if kwargs["universal_newlines"] or kwargs.get("text") is True:
            kwargs.setdefault("bufsize", 1)

        if utils.Platform.name() == "windows" and "pythonw" in sys.executable.lower():
            # Windows 7 has an issue with making subprocesses
            # if the stdin handle is None, so pass the PIPE
            kwargs.setdefault("stdin", subprocess.PIPE)

            # If this is a pythonw process, because there is no current window
            # for stdout, any subprocesses will try to create a new window
            kwargs.setdefault("creationflags", CREATE_NO_WINDOW)

        super().__init__(args, **kwargs)
