import json
import os

var_names = [
    "OS_AGNOSTIC",
    "OS_SPECIFIC",
    "ALIAS_SPECIFIC",
    "VAR_EXPAND_B",
    "FROM_VAR_EXPAND_B",
]

result = {}
for var_name in var_names:
    result[var_name] = os.getenv(var_name, "<UNSET>")

print(json.dumps(result, indent=4))
