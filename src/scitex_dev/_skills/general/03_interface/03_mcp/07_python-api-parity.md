---
description: |
  [TOPIC] Interface Mcp Python Api Parity
  [DETAILS] SciTeX MCP ↔ Python API parity — same logical name, same arg names/types, same JSON output shape. Concrete contract with examples.
tags: [scitex-general-interface-mcp-python-api-parity]
---

# §6. Python API ↔ MCP parity

Every MCP tool wraps a public Python API call. The two surfaces must agree.

## Naming convention

Public Python API `scitex_<pkg>.<verb>_<noun>(...)` ↔ MCP tool `<pkg>_<verb>_<noun>(...)`.

| Python                                    | MCP                       |
|-------------------------------------------|---------------------------|
| `scitex_io.save(obj, path)`               | `io_save`                 |
| `scitex_io.list_formats()`                | `io_list_formats`         |
| `scitex_stats.run_test(*groups, kind=…)`  | `stats_run_test`          |
| `scitex_dev.bulk_rename(config)`          | `dev_bulk_rename`         |

## Argument parity

Same names, same types. Don't rename `path` → `file_path` for MCP. Don't change `bool` → `int`.

```python
# Python
def save(obj: Any, path: str | Path, *, force: bool = False) -> Path: ...

# MCP wrapper — argument names match exactly
@mcp.tool()
async def io_save(obj: Any, path: str, force: bool = False) -> dict: ...
```

## JSON output shape

The MCP tool's return JSON and `<cli> --json`'s stdout must have **identical top-level keys** with **matching value types**. Whitespace and field order don't matter; key sets and types do.

```bash
# CLI side
$ scitex-io save data.csv ./out.csv --json
{"path": "./out.csv", "format": "csv", "bytes": 4096, "ok": true}

# MCP side
io_save(obj=data, path="./out.csv")
→ {"path": "./out.csv", "format": "csv", "bytes": 4096, "ok": true}
```

## Allowed differences

- MCP results MAY include MCP-specific envelope fields (`tool`, `request_id`, `idempotent`) **outside** the parity-checked payload — keep the payload itself identical.
- The CLI may add a `_human` key when `--json` is omitted; that key must NOT appear in `--json` output.
- Type coercion at the MCP boundary (e.g. `Path` → `str` in JSON) is allowed and expected.

## Why parity matters

- An agent that ran `scitex-io save data.csv ./out.csv --json` learns the output shape; calling `io_save` next should not surprise it.
- The MCP auditor ([08_audit-mcp-tools.md](08_audit-mcp-tools.md)) compares registered tool names with public Python operations to flag drift.

## Auditor hook

`scitex-dev ecosystem audit-mcp-tools` implements the §6 name comparison in
`_cli/audit/_summary/_mcp_parity.py`. It reads public package exports and
explicitly exported noun submodules. Classes and typing aliases for which
`typing.get_origin(value)` is non-`None` are not operations: for example,
`Callable[[str], str]`, `Literal["draft", "published"]`, and `list[str]` do not
need fake MCP tools. Real functions and callable instances remain in the check.
Nested operations flatten to `<noun>_<verb>`; a nested name whose function is
already exported flat is the same operation and is counted once.

The current unscoped comparison reports missing-tool drift when more than half
of discovered operations lack matching tools, and orphan-tool drift when more
than three non-skill tools lack Python operations. Matching accepts a bare API
name, a `verb_<api>` suffix, and — for a single-token API that §2 rejects as a
bare tool name (`describe`, `verify`) — an `<api>_<noun>` tool
(`describe_data`, `verify_result`). This name check does not by itself prove argument
or output equivalence; those contracts still need executable tests. Excluding
a typing alias must never suppress a missing real operation or create a
package-specific exemption.

## Paying down a large gap: the parity ratchet

A package that owes parity but is far from it (most of its operations have no
tool) records the gap instead of exempting itself:

```bash
scitex-dev ecosystem audit-mcp-tools scitex-stats --write-parity-baseline
git add .scitex/dev/mcp-parity-baseline.yaml
```

While `.scitex/dev/mcp-parity-baseline.yaml` exists, the missing-tool half of
§6 is exact: a NEW operation without a tool fails, and an entry whose operation
gained a tool (or was removed) fails until it is deleted from the file, so the
list only shrinks. The audit prints the remaining backlog
(`[ratchet] <pkg>: §6 parity backlog N/M …`). Re-recording is a deliberate,
reviewable diff — never a way to make a new gap pass.

Use `mcp_parity_exempt` only when the tools mirror external methods with no
Python counterpart by design, and `mcp_tools_allowlist` only when the MCP
surface is deliberately curated. A gap you intend to close is a ratchet.

## The orphan count is two different jobs, not one

`§6` reports "N MCP tools have no matching Python API". That single number
hides two fixes with very different costs, and estimating from the count
alone will be wrong.

**Case 1 — the API exists, the export is missing.** A real, synchronous
function already lives in the package; only the public re-export is absent.
One line.

**Case 2 — there is no Python API at all.** The behaviour exists only inside
an MCP handler. Closing this means designing a public synchronous signature
and moving the logic behind it. Hours, and a design decision.

One name can be in both states at once. Measured in scitex-cards, 2026-08-21:

| tool                 | where it lives                          | fix     |
|----------------------|-----------------------------------------|---------|
| `health`             | `_health.py` (sync) **and** `_mcp_skills.py` (async) | export |
| `dm_send`            | `_mcp_skills.py` only, async → JSON str  | design  |
| `poll_notifications` | `_mcp_skills.py` only, async → JSON str  | design  |

`health` has a genuine sync API *and* an async MCP shape over it, so for that
name the defect really is a missing export. `dm_send` has nothing behind it.

### Do not satisfy this rule by re-exporting the MCP handlers

The tempting shortcut is to re-export the `_mcp_*` functions and watch the
count drop. Do not. Those handlers are `async` and return **JSON strings**,
so the "Python API" you would publish is:

```python
result = await scitex_cards.dm_send(...)   # -> '{"ok": true, ...}'
```

That is an MCP transport shape wearing a Python API's name — callers get a
coroutine and a string to re-parse instead of a value. It is worse than the
gap it closes, and a rule that can be satisfied by making the API worse is a
rule being satisfied rather than met.

**Why this is in the rule text rather than the finding alone:** the count
reads as a burn-down list, and whoever picks it up will size it as one. They
should know before starting that it is at least two kinds of work — and that
one of the two has a wrong answer that makes the number go down.
