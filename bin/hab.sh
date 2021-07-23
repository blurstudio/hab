#!/bin/bash

# Habitat needs to modify the existing terminal's environment in some cases.
# To do this we can't use a setuptools exe and must use a script the terminal
# supports. This calls the python module cli passing the arguments to it and
# ends up calling the script file that code generates if required.

# TODO: Make this actually work

temp_sh_file="mktemp"
echo "using tempfile $temp_sh_file"

python -m habitat --script-output $temp_sh_file "$@"

if test -f "$temp_sh_file"; then
    echo "Running $temp_sh_file"
    . $temp_sh_file
    # rm -f $temp_sh_file
fi

# dir_name="$(dirname $(realpath "$0"))"

# for i in $(python $dir_name/get_envs.py "$@")
# do
#     echo "$i"
#     # export "$i"
# done

# TODO: Delete $temp_sh_file from disk

# export HAB_CONFIG_PATHS="c:\blur\dev\habitat\tests\configs\*"
# export HAB_DISTRO_PATHS="C:\blur\dev\habitat\tests\distros\*"



# :: Habitat needs to modify the existing terminal's environment in some cases.
# :: To do this we can't use a setuptools exe and must use a script the terminal
# :: supports. This calls the python module cli passing the arguments to it and
# :: ends up calling the script file that code generates if required.

# @ECHO OFF

# :: Generate a unique temp file name
# :uniqLoop
# set "tempBatchFile=%tmp%\prez~%RANDOM%.bat"
# if exist "%tempBatchFile%" goto :uniqLoop


# :: Call our worker python process that may write the temp filename
# python -m habitat --script-output %tempBatchFile% %*

# :: If the temp file was created run it and remove it
# if exist %tempBatchFile% (
#     ::echo SCRIPT FILE: %tempBatchFile%
#     call %tempBatchFile%
#     del "%tempBatchFile%"
# )

# @ECHO ON

# :: start cmd /k H:\public\mikeh\simp\prez\prez activate :projectDummy:Sc100:S0001.00
# :: start cmd /k H:\public\mikeh\simp\prez\prez activate :projectDummy:Guard
# :: echo %STUDIO_ELEMENT_TYPE%
# :: start cmd /k H:\public\mikeh\simp\prez\prez env :projectDummy:Sc100:S0001.00
# :: echo $env:STUDIO_ELEMENT_TYPE
