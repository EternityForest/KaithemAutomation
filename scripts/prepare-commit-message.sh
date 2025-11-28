#!/bin/sh

# Don't rewrite merge commits, rebases, or squash messages
case "$2" in 
  merge|squash|commit) exit 0 ;;
esac

BRANCH=$(git rev-parse --abbrev-ref HEAD)

# Skip if message already contains the branch
if grep -q "$BRANCH" "$1"; then
  exit 0
fi

# Prepend branch name and a colon
sed -i.bak "1s/^/[$BRANCH] /" "$1"

touch /dev/shm/jfdsadfghju