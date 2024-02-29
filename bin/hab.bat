:: Hab needs to modify the existing terminal's environment in some cases.
:: To do this we can't use a setuptools exe and must use a script the terminal
:: supports. This calls the python module cli passing the arguments to it and
:: ends up calling the script file that code generates if required.

@ECHO OFF

SETLOCAL ENABLEDELAYEDEXPANSION

:: Calculate the command to run python with
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

:uniqLoop
:: Generate a unique temp folder to store hab's short term temp .bat files.
:: Batch's %RANDOM% isn't so random, https://devblogs.microsoft.com/oldnewthing/20100617-00/?p=13673
:: So if you are calling hab as a batch of subprocesses, you may run into issues
:: where multiple processes use the same random folder causing the dir to get
:: removed while the later processes finish.

:: If not set default to the fast random
IF "%HAB_RANDOM%"=="" (set "HAB_RANDOM=fast")

IF "%HAB_RANDOM%" == "safe" (
    :: A safe but slower method when calling hab cli concurrently.
    for /f %%i in ('%py_exe% -c "import uuid; print(uuid.uuid4())"') do set uuid=%%i
) ELSE IF "%HAB_RANDOM%"=="fast" (
    :: Faster method to generate a random number that is not concurrent safe
    set "uuid=!RANDOM!"
) ELSE (
    :: Set uuid to HAB_RANDOM's output if it's set to anything else
    set "uuid=%HAB_RANDOM%"
    for /f %%i in ('%HAB_RANDOM%') do set uuid=%%i
)

set "temp_directory=%tmp%\hab~!uuid!"

:: If the folder already exists, re-generate a new folder name
if exist "!temp_directory!" goto :uniqLoop

:: Create the launch and config filenames we will end up using
mkdir !temp_directory!
:: There is a chance that between checking if the directory exists and trying
:: to create it, another process created it, Check if that occurred and generate
:: a new temp_directory if so
if errorlevel 1 goto :uniqLoop

set "temp_launch_file=!temp_directory!\hab_launch.bat"
set "temp_config_file=!temp_directory!\hab_config.bat"

:: Call our worker python process that may write the temp filename
%py_exe% -m hab --script-dir "!temp_directory!" --script-ext ".bat" %*

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
@RMDIR /S /Q !temp_directory!

ENDLOCAL

:: Ensure the errorlevel is reported to the calling process. This is needed
:: when calling hab via subprocess/QtCore.QProcess calls to receive errorlevel
@exit /b %ERRORLEVEL%
