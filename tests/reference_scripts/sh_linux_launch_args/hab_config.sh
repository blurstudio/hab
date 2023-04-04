# Customize the prompt
export PS1="[not_set/child] $PS1"

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
    "/usr/local/bin/maya" "$@";
}
export -f maya;

function mayapy() {
    "/usr/local/bin/mayapy" "$@";
}
export -f mayapy;

function pip() {
    /usr/local/bin/mayapy -m pip "$@";
}
export -f pip;


# Run the requested command
pip list

exit
