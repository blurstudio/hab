:: Hab needs to modify the existing terminal's environment in some cases.
:: To do this we can't use a setuptools exe and must use a script the terminal
:: supports. This calls the python module cli passing the arguments to it and
:: ends up calling the script file that code generates if required.

@ECHO OFF

:: Generate a unique temp file name
:uniqLoop
set "temp_directory=%tmp%\hab~%RANDOM%"
if exist "%temp_directory%" goto :uniqLoop

:: Create the launch and config filenames we will end up using
mkdir %temp_directory%
set "temp_launch_file=%temp_directory%\hab_launch.bat"
set "temp_config_file=%temp_directory%\hab_config.bat"

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
%py_exe% -m hab --script-dir "%temp_directory%" --script-ext ".bat" %*
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

:: Remove the temp directory and its contents
RMDIR /S /Q %temp_directory%

@ECHO ON
