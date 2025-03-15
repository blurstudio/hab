#!/usr/bin/env bash

# This script is a workaround for not being able to call `hab launch`` and `hab env`
# automatically from using subprocess in pytest. The developer should manually
# run this script and verify that all steps can be completed successfully.

# Hab will always output this text for the command we are calling
EXPECTED_OUTPUT="Running...
<module 'sys' (built-in)>"

# Configure hab
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HAB_PATHS="$SCRIPT_DIR/../site_main.json"

RED='\033[0;31m'
GRN='\033[0;32m'
NC='\033[0m' # No Color

# Guide the dev through the testing process
echo "Manual test of hab env. Manyally run the following commands and verify the output."
echo -e "Text in ${RED}red${NC} should be copied into a prompt and run."
echo -e "Text in ${GRN}green${NC} is the output from running the command."
echo -e "Until noted you should always see '[app/aliased]' as part of the shell's prompt. If this goes away the test is a failure."
echo "1. Check the shell options managed by the 'set' command."
echo -e "$ ${RED}echo \$-${NC}"
echo -e "You should see something like ${GRN}himBHs${NC}. Verify that it doesn't contain ${GRN}e${NC}."
echo "2. Verify that causing a error in bash doesn't exit the hab env."
echo -e "$ ${RED}something-not-valid${NC}"
echo -e "${GRN}bash: something-not-valid: command not found${NC}"
echo "3. Run the as_str alias which calls python and runs a command."
echo -e "$ ${RED}as_str -c \"import sys;print(sys);sys.exit(5)\"${NC}"
echo -e "${GRN}<module 'sys' (built-in)>${NC}"
echo "Verify that the expected return code was returned."
echo -e "$ ${RED}echo \$?${NC}"
echo -e "${GRN}5${NC}"
echo "4. Check no error return code is respected"
echo -e "$ ${RED}as_str -c \"import sys;print(sys);sys.exit(0)\"${NC}"
echo -e "${GRN}<module 'sys' (built-in)>${NC}"
echo -e "$ ${RED}echo \$?${NC}"
echo -e "${GRN}0${NC}"
echo "Exit the hab env sub-shell. This removes '[app/aliased]' from the prompt."
echo -e "$ ${RED}exit${NC}"
hab env app/aliased
