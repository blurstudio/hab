@ECHO OFF
REM This script is the alias command for batch. We can't define a function in
REM memory that can be called from the command prompt like in other shells.

REM Set alias specific environment variables that only persist for while
REM this script is running.
SETLOCAL
set "PATH=%PATH%;{{ config_root }}/distros/aliased/2.0/PATH/env/with  spaces;//example/shared_resources/with spaces"

REM Run alias command
python {{ config_root }}/distros/aliased/2.0/list_vars.py %*

REM Clear the alias specific environment variables before exiting the script
ENDLOCAL
@ECHO ON
