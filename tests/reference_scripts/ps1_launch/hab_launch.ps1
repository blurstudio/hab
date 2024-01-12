powershell.exe -ExecutionPolicy Unrestricted -File "{{ tmpdir / "hab_config.ps1" }}"
exit $LASTEXITCODE
