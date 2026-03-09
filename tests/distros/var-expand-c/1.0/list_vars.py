import json
import os

var_names = [
    "EXPAND_WILD_PRE",
    "EXPAND_C",
    "EXPAND_WILD_POST",
    "EXPAND_LINUX_PRE",
    "EXPAND_LINUX_POST",
    "EXPAND_WINDOWS_PRE",
    "EXPAND_WINDOWS_POST",
    "MERGE_C",
    "EXPAND_ALIAS_PRE",
    "EXPAND_ALIAS_POST",
    "PY_EXPAND_WILD",
    "PY_EXPAND_LINUX",
    "PY_EXPAND_WINDOWS",
]

result = {}
for var_name in var_names:
    result[var_name] = os.getenv(var_name, "<UNSET>")

print(json.dumps(result, indent=4))
