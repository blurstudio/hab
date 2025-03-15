# Manual tests

There are some tests that we haven't been able to get working automatically via pytest.
These scripts should be manually run in the correct shell and platform and the output
verified.

# test_env.sh

This tests the `hab env` command in bash on both windows and linux. Follow the
instructions printed when running the script and verify the output of each command
run.

# test_launch.sh

This tests the `hab launch` command in bash on both windows and linux. This test
requires no user input but won't run when called by pytest. You should see it test
several exit codes and is only considered successful if you see the final message
printed `'hab launch' testing completed successfully.`
