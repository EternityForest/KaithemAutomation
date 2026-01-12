#!/bin/bash

fileList=$(git diff --diff-filter=d --cached --name-only | grep -E '\.(js|vue|mjs|ts)$')
#exclude any files with thirdparty in the path
fileList=$(echo "$fileList" | grep -v "thirdparty")

if [ ${#fileList} -lt 1 ]; then
    echo -e "You have no staged files that this hook can check.\n"
    exit
fi


npx eslint --fix ${fileList[*]} -c eslint.config.mjs "$@"
if [ $? -ne 0 ]; then
    echo -e "\nPlease fix the above linting issues before committing.\n"
    exit 1
fi