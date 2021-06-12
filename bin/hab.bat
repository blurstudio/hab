:: Habitat needs to modify the existing terminal's environment in some cases.
:: To do this we can't use a setuptools exe and must use a script the terminal
:: supports. This calls the python module cli passing the arguments to it and
:: ends up calling the script file that code generates if required.

@ECHO OFF

:: Generate a unique temp file name
:uniqLoop
set "tempBatchFile=%tmp%\prez~%RANDOM%.bat"
if exist "%tempBatchFile%" goto :uniqLoop


:: Call our worker python process that may write the temp filename
python -m hab --script-output %tempBatchFile% %*

:: If the temp file was created run it and remove it
if exist %tempBatchFile% (
    ::echo SCRIPT FILE: %tempBatchFile%
    call %tempBatchFile%
    del "%tempBatchFile%"
)

@ECHO ON

:: start cmd /k H:\public\mikeh\simp\prez\prez activate :projectDummy:Sc100:S0001.00
:: start cmd /k H:\public\mikeh\simp\prez\prez activate :projectDummy:Guard
:: echo %STUDIO_ELEMENT_TYPE%
:: start cmd /k H:\public\mikeh\simp\prez\prez env :projectDummy:Sc100:S0001.00
:: echo $env:STUDIO_ELEMENT_TYPE
