---
description: |
  [TOPIC] Ecosystem
  [DETAILS] SciTeX package registry and sync operations. ECOSYSTEM is the canonical dict of all packages with local paths, PyPI names, and GitHub repos. sync_local reinstalls via pip install -e. sync_host/sync_all push via SSH. pull_local/remote_commit handle reverse sync.
tags: [scitex-dev-ecosystem]
---

# Ecosystem Management

## ECOSYSTEM

Bundled package roster. It is not an inventory of callable installed providers;
installed discovery and operator configuration are separate.

```python
from scitex_dev import ECOSYSTEM

print(ECOSYSTEM["scitex-io"])  # Inspect current metadata rather than a copied snapshot.
```

## get_all_packages / get_local_path

```python
from scitex_dev import get_all_packages, get_local_path

get_all_packages()               # list[str] of all package names
get_local_path("scitex-io")      # Path("~/proj/scitex-io").expanduser()
```

## sync_local

Reinstall local packages via `pip install -e .`

```python
from scitex_dev import sync_local
```

Signature reference (internal injection hooks omitted; not an invocation):

```text
sync_local(packages: 'list[str] | None' = None, confirm: 'bool' = False, config: 'DevConfig | None' = None, jobs: 'int' = 1, on_progress=None) -> 'dict[str, Any]'
```

```python
# Preview
sync_local(confirm=False)

# Execute
sync_local(packages=["scitex-io", "scitex-stats"], confirm=True)
```

## sync_host

Sync packages to a remote SSH host (git stash, git pull, pip install -e .).

```python
from scitex_dev import sync_host
from scitex_dev import HostConfig
```

Signature reference (internal injection hooks omitted; not an invocation):

```text
sync_host(host: 'HostConfig', packages: 'list[str] | None' = None, stash: 'bool' = True, install: 'bool' = True, safe: 'bool' = True, confirm: 'bool' = False, config: 'DevConfig | None' = None) -> 'dict[str, Any]'
```

## sync_all

Sync packages across all enabled hosts in parallel.

```python
from scitex_dev import sync_all
```

Signature reference (internal injection hooks omitted; not an invocation):

```text
sync_all(hosts: 'list[str] | None' = None, packages: 'list[str] | None' = None, stash: 'bool' = True, install: 'bool' = True, safe: 'bool' = True, confirm: 'bool' = False, config: 'DevConfig | None' = None) -> 'dict[str, Any]'
```

```python
# Dry run across all hosts
preview = sync_all(confirm=False)
for host, pkgs in preview.items():
    for pkg, info in pkgs.items():
        print(host, pkg, info["commands"])

# Execute on specific host
sync_all(hosts=["spartan"], confirm=True)
```

## sync_tags

Push local git tags to origin for all packages.

```python
from scitex_dev import sync_tags
```

Signature reference (internal injection hooks omitted; not an invocation):

```text
sync_tags(packages: 'list[str] | None' = None, confirm: 'bool' = False, config: 'DevConfig | None' = None) -> 'dict[str, Any]'
```

## pull_local

Pull latest from origin to local repos.

```python
from scitex_dev import pull_local
```

Signature reference (internal injection hooks omitted; not an invocation):

```text
pull_local(packages: 'list[str] | None' = None, confirm: 'bool' = False, stash: 'bool' = True, config: 'DevConfig | None' = None) -> 'dict[str, Any]'
```

## remote_diff

Show uncommitted changes on remote SSH hosts (read-only).

```python
from scitex_dev import remote_diff
```

Signature reference (internal injection hooks omitted; not an invocation):

```text
remote_diff(host: 'str | None' = None, packages: 'list[str] | None' = None, config: 'DevConfig | None' = None) -> 'dict[str, Any]'
```

## remote_commit

Commit dirty changes on remote host and push to origin.

```python
from scitex_dev import remote_commit
```

Signature reference (internal injection hooks omitted; not an invocation):

```text
remote_commit(host: 'str', packages: 'list[str] | None' = None, message: 'str | None' = None, push: 'bool' = True, confirm: 'bool' = False, config: 'DevConfig | None' = None) -> 'dict[str, Any]'
```

## CLI

```bash
# List ecosystem packages
scitex-dev ecosystem list
scitex-dev ecosystem list --versions
scitex-dev ecosystem list --json

# Sync
scitex-dev ecosystem sync              # dry-run (preview)
scitex-dev ecosystem sync --confirm   # execute (not available via click; use Python API)
scitex-dev ecosystem sync-local       # pip install -e . locally

# Pull and commit
scitex-dev ecosystem pull             # git pull locally
scitex-dev ecosystem commit           # commit on remote hosts
scitex-dev ecosystem diff             # show remote diffs

# Fix mismatches
scitex-dev ecosystem validate-versions --dry-run
scitex-dev ecosystem fix-mismatches

# Dashboard — the canonical `gui` group (§12 19_gui-commands.md)
scitex-dev gui open --port 8050       # auto-serve (detached) + open a browser
scitex-dev gui serve                  # foreground, headless
scitex-dev gui status                 # running? where?
scitex-dev gui stop --yes
scitex-dev gui list -vv               # same state, as a terminal table
```
