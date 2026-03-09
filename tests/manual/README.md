# Manual tests

There are some tests that we haven't been able to get working automatically via pytest.
These scripts should be manually run in the correct shell and platform and the output
verified.

# test_env.sh

This tests the `hab env` command in bash on both windows and linux. Follow the
instructions printed when running the script and verify the output of each command
run. This workflow is now tested by tests/test_launch.py but this documents how
hab's bash scripts configure the shell.
