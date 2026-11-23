---
description: |
  [TOPIC] Rename content previews and writes
  [DETAILS] Interpret original-match regex snippets and matched-occurrence counts, and verify that unchanged replacement text preserves file bytes and metadata while existing preflight guards remain active.
tags: [scitex-dev-rename-content]
---

# Rename content previews and writes

## Regex preview snippets

Regex preview expands replacement strings from the original match, preserving
lookaround context, captured groups and zero-width insertion semantics. A snippet
shows the matched text and that match's replacement, not the complete changed
line or file. Each file reports at most twenty snippets, with `before` and
`after` each limited to two hundred characters; the total match count and live
whole-file replacement are not truncated. The `regex_context` controls in
`tests/scitex_dev/rename/test_steps.py` compare explicit expected snippets,
preview file preservation and actual applications in real clean Git fixtures.

## Unchanged replacement text

The literal and regex writers in `rename/steps.py` compare generated replacement
text with the text already read from the file. Equal text causes no content
write. Identity replacements such as literal `needle` to `needle`, or regex
`(needle)` to `\1`, retain the file's bytes, inode and modification time.

Match reporting is unchanged: `summary.content_matches` counts selected matching
occurrences and `summary.content_files` counts files with those matches, even
when replacement text is identical. These values are not filesystem write
counts. A preview retains its existing match records and snippets.

The `content_noop` controls in `tests/scitex_dev/rename/test_steps.py` cover
literal and regex identity replacements with LF and CRLF files, real changes,
no-match files and a skipped regex file. They verify exact bytes and metadata,
sibling preservation and preview/application match counts in real clean Git
fixtures. A known old timestamp makes unwanted writes observable without sleeps.

Default text reads normalize line endings; avoiding an unchanged-text write also
preserves CRLF bytes in these identity cases. This does not establish general
newline/encoding preservation for nonidentity changes. Existing Git, dirty-tree
and permission preflight checks still run before content application. This is
not qualification of sudo writes or every filesystem/platform.

See [bulk rename](15_rename.md) for operation guards and result handling.
