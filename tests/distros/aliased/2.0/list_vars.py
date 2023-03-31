import os
import sys


def print_var(var):
    print("{}: {}".format(var, os.getenv(var, '[UNSET]')))


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
