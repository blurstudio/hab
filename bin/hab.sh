#!/bin/bash

# Habitat needs to modify the existing terminal's environment in some cases.
# To do this we can't use a setuptools exe and must use a script the terminal
# supports. This calls the python module cli passing the arguments to it and
# ends up calling the script file that code generates if required.

# TODO: Make this actually work

dir_name="$(dirname $(realpath "$0"))"

for i in $(python $dir_name/get_envs.py "$@")
do
    echo "$i"
    # export "$i"
done
