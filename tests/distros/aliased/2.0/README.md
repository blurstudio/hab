# Alias definitions

This example shows different ways to define aliases. Ultimately all aliases are
converted to match the "as_dict" example, but you can use the other methods to
define simple aliases. The "as_str" option should only be used if you don't need
to pass any arguments to ensure the command is properly escaped. If an alias is
not defined as a dict, the value is placed under the "cmd" key.

## Dict properties

There are a few reserved properties that are handled by hab, any properties not
listed here are preserved in the hab data and freeze so plugins can make use of
them.

### cmd
This is the command that is run when the alias is invoked by the user. This can
be a simple string if you just need to call an application. If you need to pass
any arguments, you should use a list of strings. See how subprocess.Popen handles
lists of strings. When calling an alias, you can pass any additional arguments
and they will be added to the end of "cmd".

### environment

Environment variable modifications to apply only when this alias is being executed.
This contains a standard environment variable dictionary. These environment
variables are set before cmd is called, and reset before the alias exits. Like
global environment variables, this will replace any system defined versions of
that environment variable, however if the variable is defined in the global hab
configuration, that will be used as the base.
