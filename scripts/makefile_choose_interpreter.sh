#!/bin/bash

# This script returns the current interpreter for the venv.
# Otherwise, it gives you the one in the project folder .venv
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ -z "${VIRTUAL_ENV}" ]; then
    echo "$VIRTUAL_ENV/bin/python"
else
    # If it does not exist, make it exist.
    # if [ ! -d ./venv ]; then
    #     virtualenv --system-site-packages .venv > /dev/null 2>&1 &
    # fi
    echo ".venv/bin/python"
fi
