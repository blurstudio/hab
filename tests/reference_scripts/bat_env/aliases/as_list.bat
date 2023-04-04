@ECHO OFF
REM This script is the alias command for batch. We can't define a function in
REM memory that can be called from the command prompt like in other shells.

python {{ config_root }}/distros/aliased/2.0/list_vars.py %*

@ECHO ON
