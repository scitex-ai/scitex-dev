#!/usr/bin/env bash
# Run a test child without repository-local variables exported by Git hooks.
# Git documents this exact list for foreign-repository operations:
# https://git-scm.com/docs/githooks#_description
set -euo pipefail

if [[ "$#" -eq 0 ]]; then
    echo '_git_local_env.sh: child command required' >&2
    exit 2
fi

if ! local_names="$(git rev-parse --local-env-vars)"; then
    echo '_git_local_env.sh: cannot resolve Git repository-local environment' >&2
    exit 2
fi
while IFS= read -r name; do
    if [[ ! "$name" =~ ^GIT_[A-Z0-9_]+$ ]]; then
        echo '_git_local_env.sh: invalid repository-local environment name' >&2
        exit 2
    fi
    unset "$name"
done <<< "$local_names"

# Other variables, including the selected interpreter, HOME, author identity
# and provider configuration, stay exactly as supplied by the caller.
exec "$@"
