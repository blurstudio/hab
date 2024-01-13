# Customize the prompt
function PROMPT {"[$env:HAB_URI] $(Get-Location)>"}

# Setting global environment variables:
{% for key, value in hab_cfg.environment.items() %}
{% if value %}
    {% set value = utils.Platform.collapse_paths(value) %}
    {% set value = formatter.format(value, key=key, value=value) %}
$env:{{ key }}="{{ value }}"
{% else %}
Remove-Item Env:\\{{ key }} -ErrorAction SilentlyContinue
{% endif %}
{% endfor %}
{% if freeze %}
$env:HAB_FREEZE="{{ freeze }}"
{% endif %}

{% if hab_cfg.aliases is defined %}
# Create aliases to launch programs:
{% for alias, cfg in hab_cfg.aliases.items() %}
function {{ alias }}() {
    {% set alias_env = cfg.get("environment", {}) %}
    {% if alias_env %}
    {% set alias_norm = alias.replace('-', '_') %}
    # Set alias specific environment variables. Backup the previous variable
    # value and export status, and add the hab managed variables
    $hab_bac_{{ alias_norm }} = Get-ChildItem env:
    {% for k, v in alias_env.items() %}
    {% if v %}
        {% set v = utils.Platform.collapse_paths(v) %}
        {% set v = formatter.format(v, key=key, value=v) %}
    $env:{{ k }}="{{ v }}"
    {% else %}
    Remove-Item Env:\\{{ k }} -ErrorAction SilentlyContinue
    {% endif %}
    {% endfor %}

    # Run alias command
    {% endif %}
    {{ hab_cfg.shell_escape(ext, cfg["cmd"]) }} $args
    {% if alias_env %}

    # Restore the previous environment without alias specific hab variables by
    # removing variables hab added, then restore the original variable values.
    {% for k, v in alias_env.items() %}
    Remove-Item Env:\\{{ k }} -ErrorAction SilentlyContinue
    {% endfor %}
    $hab_bac_{{ alias_norm }} | % { Set-Item "env:$($_.Name)" $_.Value }
    {% endif %}
}

{% endfor %}
{% endif %}

{% if launch_info %}
# Run the requested command
{{ launch_info.key }}{{ launch_info.args }}
# Ensure the exit-code is reported to the calling process.
exit $LASTEXITCODE
{% endif %}
