# Habitat needs to modify the existing terminal's environment in some cases.
# To do this we can't use a setuptools exe and must use a script the terminal
# supports. This calls the python module cli passing the arguments to it and
# ends up calling the script file that code generates if required.

# Generate a unique temp file name
$temp_ps_file=[System.IO.Path]::GetTempFileName()
# Remove the file that was created, we don't want it at this point.
# Also it will cause problems if we fill all of these slots
Remove-Item $temp_ps_file
# Rename the file extension to .ps1
$temp_file=[System.IO.Path]::ChangeExtension($temp_file, "ps1")
echo "%temp_file%"

# Call our worker python process that may write the temp filename
python -m habitat --script-output "%temp_file%" %*

# If the temp file was created run it and remove it
# if exist %temp_file% (
#    #echo SCRIPT FILE: %temp_file%
#    call %temp_file%
#    del "%temp_file%"
#)

# start cmd /k H:\public\mikeh\simp\prez\prez activate :projectDummy:Sc100:S0001.00
# start cmd /k H:\public\mikeh\simp\prez\prez activate :projectDummy:Guard
# echo %STUDIO_ELEMENT_TYPE%
# start cmd /k H:\public\mikeh\simp\prez\prez env :projectDummy:Sc100:S0001.00
# echo $env:STUDIO_ELEMENT_TYPE
