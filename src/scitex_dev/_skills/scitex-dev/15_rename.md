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

## Option-shaped patterns

The ripgrep helper binds patterns as data, including `--version` and `--help`.
End CLI options before such arguments:

```bash
scitex-dev rename-symbols --root /owned/checkout --dry-run --json -- --version renamed_version
```

Python takes strings directly. Traversal, exclusions and fallback are unchanged.
Real-backend controls: `tests/scitex_dev/rename/test_filters.py`.
Filename handling: [guide](16_rename-ripgrep.md).
Without optional ripgrep, that test scope is unavailable. Fallback success does
not qualify ripgrep or complete traversal/ignore/regex-dialect equivalence.

## Protected content remains visible

Literal mode replaces matching text inside ordinary quoted strings too; it is
not a Python symbol-aware refactoring engine. Its default source filters protect
whole matching lines containing `db_table=`, `related_name=`, `table=`, `name=`,
`old_name=` or `new_name=`. These are substring checks, so `prog_name=` also
matches `name=`. Django-specific protections apply separately.

For example, a file containing only `prog_name="scitex-business"` is retained
unchanged by a literal rename of `scitex-business`. Its content record reports
zero replaceable matches and one protected line; preview includes an
`action="protect"` detail. `summary.content_files` counts files with replaceable
matches, while `content_protected` counts protected lines and `protected_files`
counts files containing them. Quiet CLI output appends the protected-line count
when nonzero. Protected-only files are reported without rewriting their bytes.

These reports describe matched, selected files, not every excluded path or
unreadable file. Preview line details are capped at twenty records per file.
Regex mode uses whole-file replacement without these literal-mode source/Django
line protections; it is not an equivalent way to inspect protected literals.
See [content details](15_rename-content.md) for regex snippets and unchanged-text writes.

The owning checks are in `tests/scitex_dev/rename/test_steps.py` and
`tests/scitex_dev/_cli/test__rename.py`.

## Unchanged symlink targets

`rename/steps.py` leaves a symlink intact when replacement produces the same
target text. Its record and `symlink_targets_updated` count remain selection
reports, not write counts. The `symlink_noop` controls in
`tests/scitex_dev/rename/test_safety.py` check link metadata, outside targets,
preview and actual target changes for file, directory and dangling targets.

## Application

`execute_rename` accepts `pattern`, `replacement`, `directory`, Django protection,
optional backup settings and further `RenameConfig` options such as `regex=True`.
It checks uncommitted changes before dispatching. Live operations require a safe
Git working directory and run collision/permission checks. Preview does not
require a Git repository.

File and symlink basename destinations count an existing dangling symlink as
occupied, even when its target is absent. Preview reports that collision;
normal live orchestration refuses it during preflight, before the content
replacement step. Existing regular destinations are still collisions and absent
destinations remain renameable. This check concerns file/symlink basename
collisions. Directory basename destinations have the additional checks below;
same-path replacement and concurrent changes remain outside these guarantees.
Owning controls: `tests/scitex_dev/rename/test_steps.py` exercises dangling,
regular and absent destinations with real clean Git repositories, and
`test_core.py` retains the existing collision and directory-merge controls.

For directory basename and relative-path renames, an occupied destination is mergeable only when
it is a real directory rather than a symlink. Regular-file destinations and
symlinks to missing targets, files or directories cause live preflight to refuse
before any content replacement. This prevents a destination-directory symlink
from redirecting the merge into its target. Real-directory merging and absent
destination renames retain their existing behavior. Preview counts an occupied
destination in `target_exists`; its `merged` flag is true only for a real directory.

The `directory_target` controls in `tests/scitex_dev/rename/test_steps.py` cover
all six destination states with real clean Git repositories and owned sibling
symlink targets. They check the source, destination and sibling contents. These
are destination preflight checks, not general symlink-ancestry confinement,
concurrent-change protection or direct internal step safety without orchestration.

Directory preflight uses the same destination calculation as execution: a
basename match takes priority; otherwise the pattern is applied to the path
relative to the selected root. This includes literal paths such as `alpha/pkg`
and regex replacements with capture groups. Non-directory destinations for
those relative-path matches are refused before content changes, while real
directory merges and absent destinations keep their existing behavior.
The `relative_directory_target` controls in
`tests/scitex_dev/rename/test_steps.py` use both pattern modes across all six
destination states with owned sibling targets and real clean Git repositories.



Application is sequential, not a transaction across all selected files and
paths. The orchestrator in `rename/core.py` calls each step in order; the I/O
helpers in `rename/io.py` write or move individual paths. No rollback restores
earlier changes after a later step fails. Preflight collision/permission checks
do not make the complete operation atomic. Inspect result errors and conflicts,
and use reviewed Git state or a verified backup for recovery.

The public CLI is available under the umbrella when its Dev adapter is installed:

```bash
scitex dev rename-symbols alpha beta --root /path/to/checkout --dry-run --json
scitex dev rename-symbols alpha beta --root /path/to/checkout --yes
scitex dev rename-symbols 'alpha_(\w+)' 'beta_\1' --root /path/to/checkout --regex --dry-run
```

Replace the example path with the intended checkout and inspect the preview
before applying. Standalone bootstrap: `scitex-dev rename-symbols`.

The CLI treats a returned `RenameResult.error` as an operation failure in text,
quiet and JSON modes, exiting 1. Text and quiet modes emit the error on stderr.
JSON keeps the standard Result envelope: `success` is false, `error` contains the
refusal and `data` preserves the full rename result, including its `error` field.
Successful JSON keeps the result under `data` and exits 0. JSON takes priority
when combined with `--quiet`; successful quiet summaries retain their format.

This covers returned refusals such as dirty/non-Git roots and occupied rename
destinations. Unexpected exceptions keep the existing wrapper's classifications
and exit policy. A dry run remains a preview plan whose collision records can be
inspected before application; this change does not make those plan records a
live refusal. Source: `_cli/_rename.py` and the shared Result formatter.
The `rename_verdict` controls in `tests/scitex_dev/_cli/test__rename.py` exercise
all four output-mode combinations with real guarded and successful fixtures.


`--allow-dirty` explicitly bypasses the uncommitted-change check; it is not a
restoration mechanism. Swapping search and replacement does not generally undo
an operation: `alpha beta` becomes `beta beta`, then `alpha alpha` on a reverse
replacement. Restore from reviewed version-control state or a verified backup.

Piped symlink targets are operands; see `rename/io.py` and
`tests/scitex_dev/rename/test_io.py`. Sudo authentication is unqualified.
