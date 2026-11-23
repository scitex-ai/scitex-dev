---
description: |
  [TOPIC] Rename I/O destination semantics
  [DETAILS] Preserve exact piped move destinations, distinguish low-level moves from public directory merging, and scope real unprivileged adapter verification.
tags: [scitex-dev-rename-io]
---

# Rename I/O destination semantics

The low-level move helper uses GNU `mv -T --` for piped moves so the destination
is the exact path, matching the local `Path.rename` target behavior. An existing
directory is not interpreted as a container for the source. File/symlink moves
onto real directories refuse; a file/symlink can replace a destination symlink
without following it. A directory can replace an empty directory, but not a
nonempty one. Public deliberate directory merging remains a separate step in
`rename/steps.py`.

The `move_exact` controls in `tests/scitex_dev/rename/test_io.py` compare real
unprivileged GNU moves with local operations across those destination states.
They assert exact payloads, link text, inodes and modification times, including
protected sibling and outside targets. This is same-filesystem GNU/Linux adapter
coverage, not sudo authentication, race safety, cross-filesystem atomicity or
qualification of other platforms' `mv` options.

See [bulk rename](15_rename.md) for public preflight guards and result handling.
