@ECHO OFF
REM Customize the prompt
set "PROMPT=[not_set/child] $P$G"

REM Setting global environment variables:
set UNSET_VARIABLE=
set "TEST=case"
set "FMT_FOR_OS=a;b;c:%PATH%;d"
set ALIASED_GLOBAL_E=
set "ALIASED_GLOBAL_B=Global B"
set "ALIASED_GLOBAL_C=Global C"
set "ALIASED_GLOBAL_D=Global D"
set "ALIASED_GLOBAL_F=Global F"
set "ALIASED_GLOBAL_A=Global A"
set "HAB_URI=not_set/child"
set "HAB_FREEZE={{ freeze }}"

REM Prepend the aliases directory to path so they can be called from the prompt
set "PATH={{ tmpdir / "aliases" }};%PATH%"

REM Run the requested command
CALL as_str -c "print('Running...');import sys;print('sys', sys)"
@REM The alias we just called restored echo, so re-disable it
@ECHO OFF

exit
@ECHO ON
