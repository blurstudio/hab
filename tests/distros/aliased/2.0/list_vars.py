import os
import sys


def print_var(var):
    # Get the value from the environment
    value = os.getenv(var, '<UNSET>')
    if value != '<UNSET>':
        # Split it on path sep to ensure it is correctly generated
        value = value.split(os.path.pathsep)

    print("{}: {}".format(var, value))


print('sys.argv: {}'.format(sys.argv))

# Print expected environment variable values
print(' Env Vars: '.center(80, '-'))
print_var("ALIASED_GLOBAL_A")
print_var("ALIASED_GLOBAL_B")
print_var("ALIASED_GLOBAL_C")
print_var("ALIASED_GLOBAL_D")
print_var("ALIASED_GLOBAL_E")
print_var("ALIASED_LOCAL")
print(''.center(80, '-'))
