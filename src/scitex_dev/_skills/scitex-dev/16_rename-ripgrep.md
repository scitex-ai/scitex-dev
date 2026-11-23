---
description: |
  [TOPIC] Rename ripgrep discovery
  [DETAILS] Preserve filename boundaries in real ripgrep content discovery and distinguish backend coverage from general traversal or platform equivalence.
tags: [scitex-dev-rename-ripgrep]
---

# Rename ripgrep discovery

The optional ripgrep backend in `rename/filters.py::_rg_find_content_matches`
requests NUL-delimited filenames and decodes each filename with `os.fsdecode`.
It consumes bytes so text newline normalization cannot alter carriage returns.
A filename containing a line break remains one path; its components must not
be interpreted as separate matching files. Results remain sorted for stable
preview/application IDs. Existing exclusions, 60-second timeout and fallback
on backend failure remain unchanged.

The `rg_filename` controls in `tests/scitex_dev/rename/test_filters.py` use a
real installed ripgrep and owned clean Git fixtures. They assert exact backend
selection, public preview paths, preview byte/inode/mtime preservation, and
application content for ordinary, LF, CR, tab and Unicode line-separator names.
A crafted nested filename contains the absolute spelling of an owned sibling
sentinel after a newline: preview must preserve both files and application must
change only the actual matching file inside the selected root.

This establishes filename framing for these cases, not a general path-confinement
policy. Non-UTF-8 filenames, other platforms/tool versions, full ignore/traversal
and regex-dialect equivalence need separate evidence. Without optional ripgrep,
these backend controls are unavailable; Python fallback success does not qualify
them. See [bulk rename](15_rename.md) for operation guards and result handling.
