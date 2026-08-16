#!/usr/bin/env bash
# Enforces Conventional Commits (https://www.conventionalcommits.org) on the
# first line of a commit message. Invoked by pre-commit's commit-msg stage
# (see .pre-commit-config.yaml), which passes the path to the commit message
# file as $1.
set -euo pipefail

message_file="$1"
first_line=$(head -n 1 "$message_file")

# type(optional scope)(optional !): description
pattern='^(build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test)(\([a-z0-9./_-]+\))?!?: .+'

if [[ ! "$first_line" =~ $pattern ]]; then
  echo "Commit message does not follow Conventional Commits:" >&2
  echo "  \"$first_line\"" >&2
  echo "Expected: <type>[(scope)][!]: <description>" >&2
  echo "type is one of: build chore ci docs feat fix perf refactor revert style test" >&2
  exit 1
fi
