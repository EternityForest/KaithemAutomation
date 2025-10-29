#!/bin/bash
set -euo pipefail

# For safety, only run this with a clean working directory.
uv lock --check
if [ -n "$(git status --porcelain)" ]; then
    echo "Working directory not clean."
    exit 1
fi

# CD to the directory one level up from where this script is.
cd "$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"/..

cp pyproject.toml pyproject.toml.bak
cp uv.lock uv.lock.bak

# Export all non-development dependency versions from uv.lock.
uv export --locked --no-hashes --no-dev --no-emit-workspace \
    --output-file pinned_requirements.txt > /dev/null


file="pinned_requirements.txt"

if grep -Eq '==.*[0-9].*[A-Za-z]' "$file"; then
  echo "❌ Error: prerelease versions detected in $file"
  echo "Lines matching ==.*[0-9].*[A-Za-z]:"
  grep -En '==.*[0-9].*[A-Za-z]' "$file"
  exit 1
fi


uv add  -r pinned_requirements.txt

# Build the package.
uv build

# Restore the original project state.
mv pyproject.toml.bak pyproject.toml
mv uv.lock.bak uv.lock
rm -f pinned_requirements.txt