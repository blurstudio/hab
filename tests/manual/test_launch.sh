#!/usr/bin/env bash

# Hab will always output this text for the command we are calling
EXPECTED_OUTPUT="Running...
<module 'sys' (built-in)>"

# Configure hab
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HAB_PATHS="$SCRIPT_DIR/../site_main.json"

# Call hab launch and ensure the correct output and exit code are generated
validate_output() {
    local expected_exit_code=$1

    echo "Testing exit code: $expected_exit_code"

    # Run the command and capture the output and exit code
    output=$(hab launch app/aliased as_str -c \
        "print('Running...');import sys;print(sys);sys.exit($expected_exit_code)")
    exit_code=$?

    # Check if the return code matches the expected value
    if [[ $exit_code -ne $expected_exit_code ]]; then
        echo "Error: 'hab launch' failed with exit code $exit_code != $expected_exit_code"
        exit 1
    fi

    # On windows strip out \r characters
    output=$(echo "$output" | sed -e 's/\r//g')

    # Check if the output matches the expected text
    if [[ "$output" != "$EXPECTED_OUTPUT" ]]; then
        echo "Error: Unexpected output from 'hab launch'"
        echo "Expected: ***********************"
        echo "$EXPECTED_OUTPUT" | cat -e
        echo "Generated: ***********************"
        echo "$output" | cat -e
        echo "***********************"
        exit 1
    fi
}

validate_output 5
validate_output 4
validate_output 0

echo "'hab launch' testing completed successfully."
