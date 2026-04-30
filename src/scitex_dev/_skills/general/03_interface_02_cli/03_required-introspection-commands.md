---
name: interface-cli-required-introspection
description: SciTeX CLI required introspection commands — `list-python-apis` and `mcp list-tools` with `-v|-vv|-vvv` verbosity levels. Mandatory on every package CLI for parity with sibling packages.
user-invocable: false
tags: [scitex-python, scitex-general, cli]
---

# §1a. Required introspection commands

Every `scitex-*` package CLI **must** expose two introspection commands so that humans and agents can discover the package's surface without reading source.

## Commands

| Command            | Lists                                       | Section anchor                                                         |
|--------------------|---------------------------------------------|------------------------------------------------------------------------|
| `list-python-apis` | Public Python API (`__all__`)               | this file + [03_interface_01_python-api/00_index.md](../03_interface_01_python-api/00_index.md) |
| `mcp list-tools`   | MCP tools registered by the package         | this file + [03_interface_03_mcp/00_index.md](../03_interface_03_mcp/00_index.md)        |

Both follow the §1 noun-verb grammar:

- `list-python-apis` — verb-noun compound leaf at top level (object: `python-apis`).
- `mcp list-tools` — `mcp` noun group, `list-tools` compound-leaf verb. (`tool` is a noun in the §1d catalog; `list-tools` bakes in the object.)

## Verbosity convention — `-v` / `-vv` / `-vvv`

Both commands accept the same `-v` ladder. Each level **adds** information; it does not replace prior levels. `--verbose` is the long-form alias (consistent with §2 universal flags).

| Level     | `list-python-apis`                | `mcp list-tools`                                            |
|-----------|-----------------------------------|-------------------------------------------------------------|
| (default) | names only                        | tool names only                                             |
| `-v`      | + signatures                      | + signature (arg names + types)                             |
| `-vv`     | + docstrings (one-line summary)   | + docstring (one-line summary)                              |
| `-vvv`    | + full docstring + source path    | + full docstring + source module path + JSON-schema arg spec |

### Examples

```bash
$ scitex-io list-python-apis
save
load
load_configs
register_saver
…

$ scitex-io list-python-apis -v
save(obj, path: str | Path, **kwargs) -> Path
load(path: str | Path, **kwargs) -> Any
…

$ scitex-io list-python-apis -vv
save(obj, path: str | Path, **kwargs) -> Path
    Save any object to disk; format inferred from extension.
…

$ scitex-io mcp list-tools
io_save
io_load
io_list_formats
io_skills_list
io_skills_get

$ scitex-io mcp list-tools -v
io_save(obj: Any, path: str) -> dict
io_load(path: str) -> dict
…

$ scitex-io mcp list-tools -vv
io_save(obj: Any, path: str) -> dict
    Save any object via scitex-io.save(); returns {path, format, bytes}.
…
```

## Required flags on these commands

In addition to the verbosity ladder, both must accept (per §2 [08_universal-flags.md](08_universal-flags.md)):

- `--json` — machine-readable output. Replaces the human format with a JSON array of objects whose fields scale with the same `-v` ladder.
- `-h`, `--help` — usage with at least one example.

## Why these are mandatory

- **Discoverability without source dives** — agents and humans can list the surface in one command per concern (Python or MCP).
- **Parity check** — `list-python-apis -v` and `mcp list-tools -v` together let the auditor (§1e [07_audit-cli.md](07_audit-cli.md)) confirm CLI ↔ MCP ↔ Python parity (§7 [13_mcp-parity.md](13_mcp-parity.md)).
- **Stable contract** — verbosity ladder is the same across all `scitex-*` packages so users don't relearn flags.

## Audit hooks

The §1e auditor should verify:

- [ ] `<cli> list-python-apis` exists and exits 0.
- [ ] `<cli> list-python-apis -v|-vv|-vvv` produce monotonically more output (each level ⊇ previous).
- [ ] `<cli> mcp list-tools` exists and exits 0.
- [ ] `<cli> mcp list-tools -v|-vv|-vvv` follow the same monotonic ladder.
- [ ] Both commands honor `--json`.
