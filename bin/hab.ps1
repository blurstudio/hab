# Habitat needs to modify the existing terminal's environment in some cases.
# To do this we can't use a setuptools exe and must use a script the terminal
# supports. This calls the python module cli passing the arguments to it and
# ends up calling the script file that code generates if required.

# Generate unique temp file names
$temp_config=[System.IO.Path]::GetTempFileName()
$temp_launch=[System.IO.Path]::GetTempFileName()

# Remove the files that were created, we don't want them at this point.
# Also it will cause problems if we fill all of these slots
Remove-Item $temp_config
Remove-Item $temp_launch
# Rename the file extension to .ps1
$temp_config=[System.IO.Path]::ChangeExtension($temp_config, "ps1")
$temp_launch=[System.IO.Path]::ChangeExtension($temp_launch, "ps1")

# Calculate the command to run python with
if ($env:HAB_PYTHON -ne $null) {
    # If HAB_PYTHON is specified, use it explicitly
    $py_exe = $env:HAB_PYTHON
}
elseif ($env:VIRTUAL_ENV -ne $null) {
    # We are inside a virtualenv, so just use the python command
    $py_exe = "python"
}
else {
    # Use system defined generic python call
    $py_exe = "py -3"
}

# Call our worker python process that may write the temp filename
Invoke-Expression "$py_exe -m habitat --file-config $temp_config --file-launch $temp_launch $args"

# Run the launch or config script if it was created on disk
if (Test-Path $temp_launch -PathType Leaf)
{
    & $temp_launch
}
elseif (Test-Path $temp_config -PathType Leaf)
{
    . $temp_config
}

# Remove the temp files if they exist
if (Test-Path $temp_launch -PathType Leaf)
{
    Remove-Item $temp_launch
}
if (Test-Path $temp_config -PathType Leaf)
{
    Remove-Item $temp_config
}
