---
description: |
  [TOPIC] Hierarchy provider discovery
  [DETAILS] Inspect installed leaf declarations when building package navigation,
  breadcrumbs or global search; separate inert metadata from SDK tree loading.
tags: [scitex-dev-hierarchy]
---

# Build navigation from owning package declarations

Start with the declarations in the environment that will consume them:

```bash
scitex-dev hierarchy list --json
scitex-dev hierarchy list --package scitex-sdk --json
```

For an explicit owned installation, use repeatable `--path DIRECTORY` arguments.
This limits metadata discovery; it neither installs packages nor changes their
import path. Root `scitex-dev --json hierarchy list` also emits JSON.

The Python equivalent is `scitex_dev.list_hierarchy_providers`. Returned rows
are shared provider metadata: name, target, owning distribution, version and
summary. Unknown versions remain unknown. Discovery never imports the provider
or SDK and never falls back to a second package inventory.

Fix invalid declarations in the owning leaf: the entry-point name must equal
its canonical distribution, one owner must not declare duplicates, and the
target must be `module:attribute`. Do not hide a conflicting declaration with a
package filter; the catalog validates the full selected search first.

A catalog is not a hierarchy tree. SDK owns record/tree validation; the umbrella
owns root/layers and each leaf owns its stable allocation. Tree loading and
admission, complete package enrollment, Docs ordering and global-search wiring
remain separate. Empty metadata is not permission to invent indices. Metadata
presence is not proof of callable code, code ownership, host enablement, access
or live availability. Use the owning API docstrings for the current contract.

Dev declares only its own stable slot (`package:scitex-dev`, `3.4` under
`scitex.intermediate`). For plain metadata without SDK imports, call
`scitex_dev.hierarchy.get_hierarchy_declarations()`. Explicit
`get_hierarchy_nodes()` needs the SDK hierarchy capability and returns one SDK
record; it raises an actionable error when that capability is absent. Combine
trusted parent records through SDK validation separately. The module docstrings describe the installed provider contract; the source
guide is `docs/hierarchy-provider-metadata.md`.
