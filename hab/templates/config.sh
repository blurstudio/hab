# Customize the prompt
export PS1="[{{ hab_cfg.uri }}] $PS1"

# Exit immediately if a command exits with a non-zero status.
# This ensures that if any exit codes are encountered it gets propagated to
# whatever originally called hab.
set -e

# Setting global environment variables:
{% for key, value in hab_cfg.environment.items() %}
{% if value %}
    {% set value = utils.Platform.collapse_paths(value, ext=ext, key=key) %}
    {% set value = formatter.format(value, key=key, value=value) %}
export {{ key }}="{{ value }}"
{% else %}
unset {{ key }}
{% endif %}
{% endfor %}
{% if freeze %}
export HAB_FREEZE="{{ freeze }}"
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
    hab_bac_{{ alias_norm }}=`export -p`
    {% for k, v in alias_env.items() %}
    {% if v %}
        {% set v = utils.Platform.collapse_paths(v, ext=ext, key=k) %}
        {% set v = formatter.format(v, key=key, value=v) %}
    export {{ k }}="{{ v }}"
    {% else %}
    unset {{ k }}
    {% endif %}
    {% endfor %}

    # Run alias command
    {% endif %}
    {{ hab_cfg.shell_escape(ext, cfg["cmd"]) }} "$@";
    {% if alias_env %}

    # Restore the previous environment without alias specific hab variables by
    # removing variables hab added, then restore the original variable values.
    {% for k, v in alias_env.items() %}
    unset {{ k }}
    {% endfor %}
    # For these changes to apply outside the function scope, we need to add the
    # global scope flag to the recorded declare statements
    eval "${hab_bac_{{ alias_norm }}//declare/declare -g}"
    {% endif %}
}
export -f {{ alias }};

{% endfor %}
{% endif %}

{% if launch_info %}
# Run the requested command
{{ launch_info.key }}{{ launch_info.args }}
{% endif %}

{% if exit and create_launch %}
exit
{% endif %}
