@ECHO OFF
REM This script is the alias command for batch. We can't define a function in
REM memory that can be called from the command prompt like in other shells.

{% set alias_env = cfg.get("environment", {}) %}
{% if alias_env %}
REM Set alias specific environment variables that only persist for while
REM this script is running.
SETLOCAL
{% for k, v in alias_env.items() %}
{% if v %}
    {% set v = utils.Platform.collapse_paths(v) %}
    {% set v = formatter.format(v, key=key, value=v) %}
set "{{ k }}={{ v }}"
{% else %}
set {{ k }}=
{% endif %}
{% endfor %}

REM Run alias command
{% endif %}
{{ hab_cfg.shell_escape(ext, cfg["cmd"]) }} %*

{% if alias_env %}
REM Clear the alias specific environment variables before exiting the script
ENDLOCAL
{% endif %}
@ECHO ON
