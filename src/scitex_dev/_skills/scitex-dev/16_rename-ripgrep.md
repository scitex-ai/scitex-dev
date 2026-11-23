---
description: |
  [TOPIC] Rename ripgrep discovery
  [DETAILS] Isolate programmatic ripgrep discovery from external tool configuration, preserve filename boundaries and distinguish backend coverage from general traversal or platform equivalence.
tags: [scitex-dev-rename-ripgrep]
---

# Rename ripgrep discovery

Literal content discovery uses ripgrep's content search when available. Regex
content discovery uses ripgrep only to list candidate files, then matches their
normalized text with Python, the same engine/read behavior used for replacement.
The internal helper's default content-search mode remains available for its
real-ripgrep controls; it is not the public regex selection predicate.

The optional ripgrep backend in `rename/filters.py::_rg_find_content_matches`
requests NUL-delimited filenames and decodes each filename with `os.fsdecode`.
It consumes bytes so text newline normalization cannot alter carriage returns.
A filename containing a line break remains one path; its components must not
be interpreted as separate matching files. Results remain sorted for stable
preview/application IDs. Existing exclusions, 60-second timeout and fallback
on backend failure remain unchanged.

The Python fallback in `rename/filters.py::find_matching_files` also returns
sorted paths, for content and non-content queries. This gives both discovery
routes the same path order when they select the same files, including the order
used to assign content IDs such as `c-000` and `c-001`. IDs are not persistent
identities: adding/removing selected paths or changing selection can shift them.

The `fallback_order` controls in `tests/scitex_dev/rename/test_filters.py` use
three file creation orders, sorted Python matching and an independently observed
unsupported-lookbehind ripgrep failure. Public regex selection now always uses
Python after candidate listing; that diagnostic failure does not choose its
engine. The controls check discovery, preview IDs, preservation and application
skipping the first or middle sorted file, not complete traversal equivalence.

Actual ripgrep absence is covered separately by the `missing_rg_safety`
controls in `tests/scitex_dev/rename/test_safety.py`. Real child processes have
Git available and no `rg` on their PATH; both executable lookup and the owning
backend's detected absence are asserted. No availability predicate is replaced.
The controls call the owning Git/safety checks and public preview/application
APIs in literal and regex modes with clean, dirty, non-Git and readonly fixtures.

With this tool profile, sorted Python discovery and preview IDs remain available.
Preview preserves bytes, inodes, modification times and modes. Clean application
honors the middle content skip ID; dirty, non-Git and readonly application
requests are refused by the existing checks and preserve fixture state. These
Linux/Git fixtures qualify actual absence for this scope, not complete backend
ignore/traversal equivalence or every environment. CLI application covers the
full selected set; content skip IDs are checked through the Python API.

The programmatic command passes `--no-config`, so `RIPGREP_CONFIG_PATH` does
not change its selection or filename output. A personal config containing
`--quiet` can suppress filenames even when ripgrep exits successfully; an
extra negative glob can hide a file that the rename configuration selected.
Rename discovery uses its explicit `RenameConfig` arguments instead. This
neither edits the external config nor disables existing ignore-file behavior;
the backend does not add `--no-ignore`.

The `rg_config` controls in `tests/scitex_dev/rename/test_filters.py` use real
child processes with owned empty, quiet and excluding-glob configs in literal
and regex modes of the internal helper. Public regex selection instead combines
file listing with Python matching. They verify exact discovery/preview, no preview
writes, and application with an unchanged sibling and config. Only those config cases
are qualified; full ripgrep configuration equivalence is not established.

The `rg_filename` controls in `tests/scitex_dev/rename/test_filters.py` use a
real installed ripgrep and owned clean Git fixtures. They assert exact backend
selection, public preview paths, preview byte/inode/mtime preservation, and
application content for ordinary, LF, CR, tab and Unicode line-separator names.
A crafted nested filename contains the absolute spelling of an owned sibling
sentinel after a newline: preview must preserve both files and application must
change only the actual matching file inside the selected root.

The `rg_byte_name` controls in that same test module cover an ordinary filename,
invalid UTF-8 bytes `0xff` and `0xfe`, and a filename combining `0xff` with LF.
On Linux with UTF-8 filesystem decoding and `surrogateescape`, `os.fsdecode`
preserves those bytes in a `Path`. Backend selection, API preview/application,
CLI JSON path round-trips and an unchanged sibling file are checked with real
ripgrep. Preview also preserves fixture bytes, inodes and modification times.
JSON represents surrogate code points with escapes; parse the JSON before
round-tripping its filename with `os.fsencode` in this filesystem environment.
This concerns filename bytes, not arbitrary non-UTF-8 file contents.

These cases establish scoped filename framing, not a general path-confinement
policy or support for every byte sequence/platform/tool version. Full ignore,
traversal and regex-dialect equivalence need separate evidence. Without optional
ripgrep, the ripgrep-specific controls are unavailable; passing fallback controls
does not qualify real-ripgrep behavior. See [bulk rename](15_rename.md) for guards and result handling.
