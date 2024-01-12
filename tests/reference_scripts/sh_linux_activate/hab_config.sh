# Customize the prompt
export PS1="[not_set/child] $PS1"

# Exit immediately if a command exits with a non-zero status.
# This ensures that if any exit codes are encountered it gets propagated to
# whatever originally called hab.
set -e

# Setting global environment variables:
unset UNSET_VARIABLE
export TEST="case"
export FMT_FOR_OS="a:b;c:$PATH:d"
unset ALIASED_GLOBAL_E
export ALIASED_GLOBAL_B="Global B"
export ALIASED_GLOBAL_C="Global C"
export ALIASED_GLOBAL_D="Global D"
export ALIASED_GLOBAL_F="Global F"
export ALIASED_GLOBAL_A="Global A"
export HAB_URI="not_set/child"
export HAB_FREEZE="{{ freeze }}"

# Create aliases to launch programs:
function as_dict() {
    # Set alias specific environment variables. Backup the previous variable
    # value and export status, and add the hab managed variables
    hab_bac_as_dict=`export -p`
    export ALIASED_LOCAL="{{ config_root }}/distros/aliased/2.0/test"

    # Run alias command
    python {{ config_root }}/distros/aliased/2.0/list_vars.py "$@";

    # Restore the previous environment without alias specific hab variables by
    # removing variables hab added, then restore the original variable values.
    unset ALIASED_LOCAL
    # For these changes to apply outside the function scope, we need to add the
    # global scope flag to the recorded declare statements
    eval "${hab_bac_as_dict//declare/declare -g}"
}
export -f as_dict;

function inherited() {
    # Set alias specific environment variables. Backup the previous variable
    # value and export status, and add the hab managed variables
    hab_bac_inherited=`export -p`
    export PATH="$PATH:{{ config_root }}/distros/aliased/2.0/PATH/env/with  spaces:/mnt/shared_resources/with spaces"

    # Run alias command
    python {{ config_root }}/distros/aliased/2.0/list_vars.py "$@";

    # Restore the previous environment without alias specific hab variables by
    # removing variables hab added, then restore the original variable values.
    unset PATH
    # For these changes to apply outside the function scope, we need to add the
    # global scope flag to the recorded declare statements
    eval "${hab_bac_inherited//declare/declare -g}"
}
export -f inherited;

function as_list() {
    python {{ config_root }}/distros/aliased/2.0/list_vars.py "$@";
}
export -f as_list;

function as_str() {
    "python" "$@";
}
export -f as_str;

function global() {
    # Set alias specific environment variables. Backup the previous variable
    # value and export status, and add the hab managed variables
    hab_bac_global=`export -p`
    export ALIASED_GLOBAL_A="Local A Prepend:Global A:Local A Append"
    export ALIASED_GLOBAL_C="Local C Set"
    unset ALIASED_GLOBAL_D

    # Run alias command
    python {{ config_root }}/distros/aliased/2.0/list_vars.py "$@";

    # Restore the previous environment without alias specific hab variables by
    # removing variables hab added, then restore the original variable values.
    unset ALIASED_GLOBAL_A
    unset ALIASED_GLOBAL_C
    unset ALIASED_GLOBAL_D
    # For these changes to apply outside the function scope, we need to add the
    # global scope flag to the recorded declare statements
    eval "${hab_bac_global//declare/declare -g}"
}
export -f global;

function maya() {
    "/usr/local/bin/maya2020" "$@";
}
export -f maya;

function mayapy() {
    "/usr/local/bin/mayapy2020" "$@";
}
export -f mayapy;

function maya20() {
    "/usr/local/bin/maya2020" "$@";
}
export -f maya20;

function mayapy20() {
    "/usr/local/bin/mayapy2020" "$@";
}
export -f mayapy20;

function pip() {
    /usr/local/bin/mayapy2020 -m pip "$@";
}
export -f pip;
