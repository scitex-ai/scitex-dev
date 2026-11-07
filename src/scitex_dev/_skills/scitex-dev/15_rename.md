---
description: |
  [TOPIC] Bulk rename
  [DETAILS] Preview or apply changes to file contents, symlink targets, symlink names, files and directories. Use current RenameConfig/RenameResult fields, inspect errors and restore from version control or verified backups rather than assuming replacement is invertible.
tags: [scitex-dev-rename]
---

# Bulk rename

The rename provider applies changes in this order: contents, symlink targets,
symlink names, file names, then directory names from deepest to shallowest.
Preview uses the same provider without applying those changes.

## Preview an owned example

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from scitex_dev import RenameConfig, bulk_rename, preview_rename

with TemporaryDirectory(prefix="scitex-rename-demo-") as directory:
    path = Path(directory) / "alpha.txt"
    path.write_text("alpha\n")
    plan = preview_rename("alpha", "beta", directory=directory)
    print(plan.dry_run, plan.error)               # True None
    print(path.read_text().strip())              # alpha: preview preserved it
    config = RenameConfig("alpha", "beta", directory=directory, dry_run=True)
    second_plan = bulk_rename(config)
    print(second_plan.dry_run)                   # True
```

`bulk_rename` receives a `RenameConfig`; put `dry_run` in that configuration,
not in a separate `bulk_rename(..., dry_run=...)` keyword.

## Configuration and result fields

`RenameConfig` requires `pattern` and `replacement`. Its defaults include
`directory="."`, `dry_run=True`, `regex=False`, `django_safe=True` and
`create_backup=False`. It also exposes path/content filters, recursion,
`extra_excludes`, `skip_ids` and `use_sudo`. Inspect actual defaults when selecting
scope; the path filters deliberately exclude archives and migrations as well as
Git and environment directories.

`RenameResult` contains:

| Field | Meaning |
|---|---|
| `dry_run`, `pattern`, `replacement`, `directory` | Operation identity |
| `contents` | Content matches/change records |
| `symlink_targets`, `symlink_names` | Symlink change records |
| `file_names`, `dir_names` | Path change records |
| `summary` | Counts and any operation warnings |
| `collisions`, `permission_errors` | Structured conflicts |
| `error` | Operation-level failure, or `None` |

Change records are dictionaries, not merely lists of filenames. Inspect `error`
and conflicts before treating an operation as successful. Definitions are in
`rename/config.py`; preview, application and configuration dispatch are in
`rename/core.py`.

## Application

`execute_rename` accepts `pattern`, `replacement`, `directory`, Django protection,
optional backup settings and further `RenameConfig` options such as `regex=True`.
It checks uncommitted changes before dispatching. Live operations require a safe
Git working directory and run collision/permission checks. Preview does not
require a Git repository.

The public CLI is available under the umbrella when its Dev adapter is installed:

```bash
scitex dev rename-symbols alpha beta --root /path/to/checkout --dry-run --json
scitex dev rename-symbols alpha beta --root /path/to/checkout --yes
scitex dev rename-symbols 'alpha_(\w+)' 'beta_\1' --root /path/to/checkout --regex --dry-run
```

Replace the example path with the intended checkout and inspect the preview
before applying. Standalone bootstrap: `scitex-dev rename-symbols`.

`--allow-dirty` explicitly bypasses the uncommitted-change check; it is not a
restoration mechanism. Swapping search and replacement does not generally undo
an operation: `alpha beta` becomes `beta beta`, then `alpha alpha` on a reverse
replacement. Restore from reviewed version-control state or a verified backup.
