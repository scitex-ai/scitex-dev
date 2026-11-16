---
description: |
  [TOPIC] Package navigation hierarchy
  [DETAILS] Discover and validate inert package hierarchy catalogs for shared
  navigation and search. Keep taxonomy separate from installed availability,
  dependency graphs and host admission. Root owns ecosystem allocations;
  domain packages continue to own their docs, skills and implementation.
tags: [scitex-general-development-package-hierarchy]
---

# Package navigation hierarchy

`scitex_dev.list_package_hierarchies()` reads installed declarations from the
`scitex_dev.hierarchy` entry-point group. `scitex-dev docs list-hierarchies
--json` and the Dev MCP tool `docs_list_hierarchies` return the same catalog
shape. SDK and host consumers should render these catalogs rather than invent
another package inventory. This is navigation metadata, not global search
indexing, a dependency graph or proof that a package is installed or enabled.

A provider declares a top-level Python package, for example:

```toml
[project.entry-points."scitex_dev.hierarchy"]
scitex = "scitex"
```

That package ships `_package_hierarchy.json` with exactly `schema_version`
(integer `1`), `root` (matching the entry-point name), and a `nodes` array.
Each node has `id`, `label`, `index`, `parent_id`, `kind`, and optionally
`distribution`. The unique root has kind `root`, index `0`, and null parent.
Its group children use positive indices such as `1`; descendants extend their
parent index by one positive segment such as `1.2`. Package nodes are leaves
and require canonical distribution names. IDs and indices are unique. Indices
are stable allocations, never installation order; absent or unallocated
packages must not be silently assigned an index.

Discovery reads a bounded JSON file without importing the provider or loading
its entry point. Callable/dotted targets, symlink resources, ambiguous package
locations, duplicate JSON fields, conflicting catalogs and malformed trees
fail explicitly. No installed providers returns an empty tuple. The optional
Python `path` argument limits metadata discovery; package lookup follows the
interpreter's normal import path. This supports ordinary installed filesystem
packages; zip-based resource loaders are not supported.

Implementation: `package_hierarchy/_schema.py` and `_discovery.py`. Behavioral
coverage: `tests/scitex_dev/package_hierarchy/test__schema.py` and `test__discovery.py` uses real
metadata directories, inert package resources and a provider that raises if
imported. Installed artifacts, live UI and full ecosystem allocations require
separate qualification; syntax/build success does not establish them.
