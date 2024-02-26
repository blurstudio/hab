:: Hab needs to modify the existing terminal's environment in some cases.
:: To do this we can't use a setuptools exe and must use a script the terminal
:: supports. This calls the python module cli passing the arguments to it and
:: ends up calling the script file that code generates if required.

@ECHO OFF

:: Generate a unique temp folder to store hab's short term temp .bat files.
:: Batch's %RANDOM% isn't so random, https://devblogs.microsoft.com/oldnewthing/20100617-00/?p=13673
:: So if you are calling hab as a batch of subprocesses, you may run into issues
:: where multiple processes use the same random folder causing the dir to get
:: removed while the later processes finish.

:: 1. To work around this issue we add the current process's PID to the filename.
:: https://superuser.com/a/1746190
for /f "USEBACKQ TOKENS=2 DELIMS=="  %%A in (`wmic process where ^(Name^="WMIC.exe" AND CommandLine LIKE "%%%%TIME%%%%"^) get ParentProcessId /value`) do set "PID=%%A"
rem echo PID: %PID%
rem timeout 10

:: 2. We also add a random number to hopefully reduce the chance of name conflicts
:uniqLoop
set "temp_directory=%tmp%\hab~%RANDOM%-%PID%"
:: If the folder already exists, re-generate a new folder name
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

:: the config scripts turn echo back on, Make sure to prefix future commands
:: with @ to prevent printing them to the console

:: Remove the temp directory and its contents
@RMDIR /S /Q %temp_directory%

:: Ensure the errorlevel is reported to the calling process. This is needed
:: when calling hab via subprocess/QtCore.QProcess calls to receive errorlevel
@exit /b %ERRORLEVEL%
