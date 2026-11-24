---
description: |
  [TOPIC] Rename content previews and writes
  [DETAILS] Interpret original-match regex snippets and matched-occurrence counts, and verify that unchanged replacement text preserves file bytes and metadata while existing preflight guards remain active.
tags: [scitex-dev-rename-content]
---

# Rename content previews and writes

## Regex text selection

Regex content selection and replacement both use Python `re.DOTALL` on text
read with `Path.read_text(errors="surrogateescape")`, including universal-newline
normalization. A match such as `needle\n` can therefore select CRLF text, and
line anchors apply to the normalized text. A raw ripgrep regex search is not an
authoritative filter for these Python operations.

When ripgrep is available, it enumerates candidate files with the existing
scope, depth, exclusions and default ignore rules; Python checks each eligible
file's content. Literal mode retains ripgrep content search. Regex mode can
read more candidates than a ripgrep regex prefilter. Missing/failed ripgrep
listing keeps the existing Python-glob fallback, whose traversal/ignore behavior
is not completely equivalent.

The `regex_text` controls in `tests/scitex_dev/rename/test_filters.py` verify
LF, CRLF and standalone-CR cases with actual ripgrep available: exact discovery,
normalized preview snippets, no preview writes and whole-file application.
They include newline/anchor cases previously missed plus ordinary, LF and
lookbehind controls. This qualifies those text cases, not arbitrary encodings
or binary content policy. Nonidentity writes retain existing normalization.

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

## Undecodable bytes in selected text

Content selection and application use `surrogateescape` for decoding, and the
local/piped content writers use it when encoding. In a UTF-8 locale, an invalid
byte such as `0xff` is carried as a surrogate code point and written back as the
same byte. An ASCII token edit can therefore preserve surrounding undecodable
bytes. Valid Unicode, including a genuine `U+FFFD`, retains its normal meaning.
The default encoding choice remains unchanged; no other encoding is guessed.

The byte controls in `tests/scitex_dev/rename/test_io.py` cover ordinary ASCII,
valid Unicode and replacement-character text, invalid prefix/suffix bytes,
truncated UTF-8 and multiple undecodable bytes. They assert exact writer output,
preview preservation and literal/regex application bytes in real clean Git
fixtures. The piped-writer adapter uses real unprivileged `tee` through the
supported runner argument; it does not qualify sudo authentication or transport.

Literal preview records can contain escaped surrogate code points. Python and
CLI JSON round-trips are scoped evidence; cross-language client handling is
unverified. Existing line-ending normalization still applies to actual changes.
These LF/UTF-8-locale cases do not establish general binary/encoding support
or arbitrary-regex byte semantics. NUL-bearing input has a separate exclusion
rule below.
Git, dirty-tree and permission guards remain active; no privilege policy changes.

## NUL-bearing input

Bulk content editing excludes input text containing NUL (`\0`) in literal and
regex modes, with or without ripgrep. The shared reader in `rename/filters.py`
returns no eligible text for that input and is also used by the final content
stage in `rename/steps.py`. Empty text remains eligible, including regex `^$`.
Read errors retain the existing skip behavior and decoding uses `surrogateescape`.

The `nul_content` controls in `tests/scitex_dev/rename/test_filters.py` cover
prefix, suffix and late NULs, ordinary and empty text, and explicit literal/regex
NUL patterns. Discovery excludes NUL input; preview reports no content matches
and preserves bytes/inodes/mtimes; application makes no content write. A literal
NUL pattern has no eligible match. A regex containing a NUL alternative can still
match ordinary text through its other alternative.

The `fallback_content` controls in `tests/scitex_dev/rename/test_safety.py`
exercise those content cases in child processes whose PATH contains only real
Git. Each asserts that ripgrep is absent, checks discovery or preview/application,
and verifies excluded bytes plus sibling/archive/outside metadata. Empty-regex
and ordinary-text edits are positive controls. JSON carries actual NUL patterns
into the Python API; OS command arguments cannot contain a literal NUL.
These fixtures do not qualify fallback Git-ignore behavior or concurrent changes.

This rule concerns content input. Existing path-renaming behavior and the low-level
writer remain available independently; a NUL-bearing file can still have its name
renamed without editing its bytes. The rule is not a complete binary-format or
encoding detector. Valid text without NUL retains the existing behavior. Matched
literal candidates now require a validation read as well as the final content read.

See [bulk rename](15_rename.md) for operation guards and result handling.
