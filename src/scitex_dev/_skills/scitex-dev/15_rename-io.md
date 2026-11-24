---
description: |
  [TOPIC] Rename I/O destination semantics
  [DETAILS] Preserve exact piped move and symlink destinations, distinguish low-level moves from public directory merging, and scope real unprivileged adapter verification.
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

## Symlink creation

The low-level creator uses GNU `ln -s -T --` for piped calls. The link path is
an exact destination, matching local `Path.symlink_to`: an existing file,
directory or symlink causes refusal. This includes a dangling link or a link
to an outside directory. Creation does not put a new link inside an occupied
directory, follow a destination directory link or force replacement. New links
retain the requested target text, including targets that do not exist.

The `link_exact` controls in `tests/scitex_dev/rename/test_io.py` cover local
and real unprivileged GNU calls for file, directory and missing target text.
They verify absent destinations and six occupied destination shapes, preserving
existing payloads, link text, inodes, mtimes and sibling/outside targets. Earlier
`link_operand` controls retain leading-hyphen and Unicode target coverage.
These checks do not qualify sudo authentication, concurrent changes, a complete
public rename transaction or other platforms' `ln` flags. Public callers that
explicitly remove/recreate links remain separate from this low-level creator.
