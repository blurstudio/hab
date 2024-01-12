# Customize the prompt
function PROMPT {"[$env:HAB_URI] $(Get-Location)>"}

# Setting global environment variables:
Remove-Item Env:\\UNSET_VARIABLE -ErrorAction SilentlyContinue
$env:TEST="case"
$env:FMT_FOR_OS="a;b;c:$env:PATH;d"
Remove-Item Env:\\ALIASED_GLOBAL_E -ErrorAction SilentlyContinue
$env:ALIASED_GLOBAL_B="Global B"
$env:ALIASED_GLOBAL_C="Global C"
$env:ALIASED_GLOBAL_D="Global D"
$env:ALIASED_GLOBAL_F="Global F"
$env:ALIASED_GLOBAL_A="Global A"
$env:HAB_URI="not_set/child"
$env:HAB_FREEZE="{{ freeze }}"

# Create aliases to launch programs:
function as_dict() {
    # Set alias specific environment variables. Backup the previous variable
    # value and export status, and add the hab managed variables
    $hab_bac_as_dict = Get-ChildItem env:
    $env:ALIASED_LOCAL="{{ config_root }}/distros/aliased/2.0/test"

    # Run alias command
    python {{ config_root }}/distros/aliased/2.0/list_vars.py $args

    # Restore the previous environment without alias specific hab variables by
    # removing variables hab added, then restore the original variable values.
    Remove-Item Env:\\ALIASED_LOCAL -ErrorAction SilentlyContinue
    $hab_bac_as_dict | % { Set-Item "env:$($_.Name)" $_.Value }
}

function inherited() {
    # Set alias specific environment variables. Backup the previous variable
    # value and export status, and add the hab managed variables
    $hab_bac_inherited = Get-ChildItem env:
    $env:PATH="$env:PATH;{{ config_root }}/distros/aliased/2.0/PATH/env/with  spaces;//example/shared_resources/with spaces"

    # Run alias command
    python {{ config_root }}/distros/aliased/2.0/list_vars.py $args

    # Restore the previous environment without alias specific hab variables by
    # removing variables hab added, then restore the original variable values.
    Remove-Item Env:\\PATH -ErrorAction SilentlyContinue
    $hab_bac_inherited | % { Set-Item "env:$($_.Name)" $_.Value }
}

function as_list() {
    python {{ config_root }}/distros/aliased/2.0/list_vars.py $args
}

function as_str() {
    python $args
}

function global() {
    # Set alias specific environment variables. Backup the previous variable
    # value and export status, and add the hab managed variables
    $hab_bac_global = Get-ChildItem env:
    $env:ALIASED_GLOBAL_A="Local A Prepend;Global A;Local A Append"
    $env:ALIASED_GLOBAL_C="Local C Set"
    Remove-Item Env:\\ALIASED_GLOBAL_D -ErrorAction SilentlyContinue

    # Run alias command
    python {{ config_root }}/distros/aliased/2.0/list_vars.py $args

    # Restore the previous environment without alias specific hab variables by
    # removing variables hab added, then restore the original variable values.
    Remove-Item Env:\\ALIASED_GLOBAL_A -ErrorAction SilentlyContinue
    Remove-Item Env:\\ALIASED_GLOBAL_C -ErrorAction SilentlyContinue
    Remove-Item Env:\\ALIASED_GLOBAL_D -ErrorAction SilentlyContinue
    $hab_bac_global | % { Set-Item "env:$($_.Name)" $_.Value }
}

function maya() {
    C:\Program` Files\Autodesk\Maya2020\bin\maya.exe $args
}

function mayapy() {
    C:\Program` Files\Autodesk\Maya2020\bin\mayapy.exe $args
}

function maya20() {
    C:\Program` Files\Autodesk\Maya2020\bin\maya.exe $args
}

function mayapy20() {
    C:\Program` Files\Autodesk\Maya2020\bin\mayapy.exe $args
}

function pip() {
    C:\Program` Files\Autodesk\Maya2020\bin\mayapy.exe -m pip $args
}


# Run the requested command
as_str -c "print('Running...');import sys;print('sys', sys)"
# Ensure the exit-code is reported to the calling process.
exit $LASTEXITCODE
