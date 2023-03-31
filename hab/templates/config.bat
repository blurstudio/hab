@ECHO OFF
REM Customize the prompt
set "PROMPT=[{{ hab_cfg.uri }}] $P$G"

REM Setting global environment variables:
{% for key, value in hab_cfg.environment.items() %}
{% if value %}
    {% set value = utils.Platform.collapse_paths(value) %}
    {% set value = formatter.format(value, key=key, value=value) %}
set "{{ key }}={{ value }}"
{% else %}
set {{ key }}=
{% endif %}
{% endfor %}
{% if freeze %}
set "HAB_FREEZE={{ freeze }}"
{% endif %}

{% if hab_cfg.aliases is defined %}
REM Prepend the aliases directory to path so they can be called from the prompt
set "PATH={{ alias_dir }};%PATH%"
{% endif %}

{% if launch_info %}
REM Run the requested command
CALL {{ launch_info.key }}{{ launch_info.args }}
@REM The alias we just called restored echo, so re-disable it
@ECHO OFF
{% endif %}

{% if exit and create_launch %}
exit
{% endif %}
@ECHO ON
