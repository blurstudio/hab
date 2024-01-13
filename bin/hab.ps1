# Hab needs to modify the existing terminal's environment in some cases.
# To do this we can't use a setuptools exe and must use a script the terminal
# supports. This calls the python module cli passing the arguments to it and
# ends up calling the script file that code generates if required.

$temp_directory=[System.IO.Path]::GetTempFileName()

# Remove this file so we can create a directory with the same name
Remove-Item $temp_directory
# Create a directory with the same name as the temp file we just deleted
New-Item -Path $temp_directory -ItemType 'Directory' | Out-Null

# Generate unique temp file names
$temp_config="$temp_directory\hab_config.ps1"
$temp_launch="$temp_directory\hab_launch.ps1"

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
# For complex launch commands like `py -3` we need to separate the command from
# additional arguments, we can't just pass the raw $py_exe variable
$py_exe, $py_args = $py_exe.split(' ')
# TODO: Test setting HAB_PYTHON to various values like `py`, `py -3` and many arguments `py -3 -u`

# Call our worker python process that may write the temp filename
& $py_exe $py_args -m hab --script-dir $temp_directory --script-ext .ps1 $args

# Run the launch or config script if it was created on disk
if (Test-Path $temp_launch -PathType Leaf)
{
    & $temp_launch
}
elseif (Test-Path $temp_config -PathType Leaf)
{
    . $temp_config
}

# Remove the temp directory if it exists
Remove-Item $temp_directory -Force -Recurse -erroraction 'silentlycontinue'

# Ensure the exit-code is reported to the calling process.
exit $LASTEXITCODE
