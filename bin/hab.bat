:: Habitat needs to modify the existing terminal's environment in some cases.
:: To do this we can't use a setuptools exe and must use a script the terminal
:: supports. This calls the python module cli passing the arguments to it and
:: ends up calling the script file that code generates if required.

@ECHO OFF

:: Generate a unique temp file name
:uniqLoop
set "temp_config_file=%tmp%\habitat~%RANDOM%"
if exist "%temp_config_file%_config.bat" goto :uniqLoop

:: Create the launch and config filenames we will end up using
set "temp_launch_file=%temp_config_file%_launch.bat"
set "temp_config_file=%temp_config_file%_config.bat"

:: Calculate the command to run python with
SETLOCAL ENABLEEXTENSIONS
IF DEFINED HAB_PYTHON (
    :: If HAB_PYTHON is specified, use it explicitly
    set py_exe=%HAB_PYTHON%
) ELSE IF DEFINED VIRTUAL_ENV (
    :: We are inside a virtualenv, so just use the python command
    set py_exe=python
) ELSE (
    :: Use system defined generic python call
    set "py_exe=py -3"
)

:: Call our worker python process that may write the temp filename
%py_exe% -m habitat --file-config "%temp_config_file%" --file-launch "%temp_launch_file%" %*
ENDLOCAL

:: Run the launch or config script if it was created on disk
if exist %temp_launch_file% (
    call %temp_launch_file%
) else (
    if exist %temp_config_file% (
        call %temp_config_file%
    )
)

:: the config scripts turn echo back on, turn it off again
@ECHO OFF

:: Remove the temp files if they exist
if exist %temp_launch_file% (
    del "%temp_launch_file%"
)
if exist %temp_config_file% (
    del "%temp_config_file%"
)

@ECHO ON
