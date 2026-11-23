---
description: |
  [TOPIC] Docs Search
  [DETAILS] Documentation retrieval and search in the current Python environment. Separate inert provider declarations from legacy docs resolution, which can import packages.
tags: [scitex-dev-docs-search]
---

# Docs Aggregation and Search

## Discovery and execution boundaries

`scitex_dev.list_doc_providers()` reads installed `scitex_dev.docs` declarations
without importing their targets or adding roster fallbacks. Duplicate names stay
visible. `docs list-providers --json` reports `declarations_only: true` and
`live_verified: false`; metadata does not establish callable or enabled providers.

`get_docs` and `build_docs` use a separate legacy mapping from
`_core.discovery.discover_packages`: entry points plus missing names from
installed packages in `ECOSYSTEM`. Default calls cache the mapping until
`invalidate_cache()`; explicit injection arguments or `use_cache=False` bypass
that cache. Duplicate names collapse in this dict; ambiguous routing remains
unresolved, not a stable provider-selection contract. Missing-entry-point hints
are DEBUG messages, not warnings.

`get_package_root` tries metadata first, then imports a target if no root was
found. `get_docs` can also import for introspection. Import initialization can
execute code and non-`ImportError` exceptions can propagate. Use the declaration
catalog for inert inspection; retrieval is not a no-execution guarantee.

Owners: `_core/discovery.py`, `doc_providers` and `_docs/docs.py`. Controls:
`tests/scitex_dev/doc_providers/test___init__.py`,
`tests/scitex_dev/_core/test_discovery.py` and
`tests/scitex_dev/_cli/test__docs_cmds.py`. These checks do not qualify fleet
profiles, provider activation, generated content or served documentation.

## get_docs

Get docs for named packages or every package in the local legacy mapping.

```python
from scitex_dev import get_docs
```

Signature reference (internal injection hooks omitted; not an invocation):

```text
get_docs(package: 'Optional[str]' = None, packages: 'Optional[list[str]]' = None, format: 'Optional[str]' = None, page: 'Optional[str]' = None) -> 'Any'
```

Resolution chain per package (fastest to slowest):
1. Pre-built `_sphinx_html/` in installed package (production)
2. Sphinx `_build/` available (existing build)
3. Introspect from available docstrings/signatures (can still fail for unavailable dependencies or providers)

```python
# Manifest overview of all packages
manifests = get_docs()

# Single package manifest
info = get_docs(package="scitex-io")
print(info["version"], info["description"])
print(info["pages"])

# HTML path
html_dir = get_docs(package="scitex-io", format="html")

# Specific page
page_data = get_docs(package="scitex-io", format="json", page="api")

# Multiple packages
results = get_docs(packages=["scitex-io", "scitex-stats"])
for pkg, data in results.items():
    print(pkg, data.get("version"))
```

## build_docs

Build docs from Sphinx source for one or all packages.

```python
from scitex_dev import build_docs
```

Signature reference (internal injection hooks omitted; not an invocation):

```text
build_docs(package: 'Optional[str]' = None, output_dir: 'Optional[Path]' = None, formats: 'Optional[list[str]]' = None) -> 'dict[str, Any]'
```

Requires `sphinx` (`pip install scitex-dev[docs]`).

```python
# Build all
build_docs()

# Build specific package
result = build_docs(package="scitex-io", formats=["html", "json"])
print(result["scitex-io"]["html"])   # path to built HTML
```

## search_docs

Simple keyword search over package page titles and introspected content.

```python
from scitex_dev import search_docs
```

Signature reference (internal injection hooks omitted; not an invocation):

```text
search_docs(query: 'str', package: 'Optional[str]' = None, packages: 'Optional[list[str]]' = None, max_results: 'int' = 10) -> 'list[dict[str, Any]]'
```

```python
hits = search_docs("save figure")
for h in hits:
    print(h["package"], h["name"], h["score"])
```

## search

Search uses four local indexes (`_docs/search.py`):
- `docs`: manifest page names/titles and package description, not page bodies.
- `api`: shallow exported members and class methods from package introspection;
  submodules are described without recursive traversal.
- `cli`: matching `console_scripts` names/targets, without loading entry points
  or enumerating their subcommands.
- `mcp`: def/docstring text in non-underscore `*.py` files directly under
  `_mcp_tools`, `mcp` or `_mcp`; this heuristic does not check tool registration.

API introspection and package-root fallback can execute import initialization.
Hits do not establish successful invocation or live availability. Complete
subcommand/tool coverage remains unresolved. Controls: `test_search.py` under
`tests/scitex_dev/_docs`; query syntax supports the following operators.

```python
from scitex_dev import search
```

Signature reference (internal injection hooks omitted; not an invocation):

```text
search(query: 'str', scope: 'Scope' = 'all', package: 'Optional[str]' = None, packages: 'Optional[list[str]]' = None, max_results: 'int' = 10, fuzzy: 'bool' = True) -> 'list[dict[str, Any]]'
```

### Query syntax

| Syntax | Meaning |
|---|---|
| `save figure` | match any term (OR) |
| `"save figure"` | exact phrase match (3x weight) |
| `+ttest statistics` | `ttest` must match; fuzzy by default |
| `stats -deprecated` | exclude results containing "deprecated" |
| `+save "to disk"` | required term + exact phrase |

Score weights: phrase=3.0, required=2.0 (including fuzzy required matches),
optional exact=1.0, optional fuzzy=0.5. `fuzzy=False` disables fuzzy term matches.

```python
# Search all scopes
results = search("save figure")

# Python API only
results = search("ttest", scope="api")

# MCP tools only, excluding deprecated
results = search("stats -deprecated", scope="mcp")

# Exact phrase match
results = search('"session decorator"')

# Required match (fuzzy by default)
results = search("+load csv")

# Scoped to single package
results = search("save", scope="api", package="scitex-io")
```

## CLI

```bash
# Search the local legacy package mapping
scitex-dev docs search "save figure"
scitex-dev docs search "ttest" --scope api
scitex-dev docs search "stats" --scope mcp --max-results 5
scitex-dev docs search '"session decorator"'
scitex-dev docs search "save figure" --json

# Docs commands
scitex-dev docs list
scitex-dev docs get scitex-io
scitex-dev docs get scitex-io --format html
scitex-dev docs search "save figure"
scitex-dev docs build scitex-io
```
