# Hierarchy provider metadata

Use `scitex-dev hierarchy list --json` when preparing package navigation,
breadcrumbs or global search. It reads installed `scitex_dev.hierarchy`
declarations in the environment running Dev. It does not search other hosts,
import provider targets, load SDK records, allocate indices or build a tree.

Leaf declarations are authoritative. A package declares one entry point whose
name is its canonical owning distribution and whose value is a direct
`module:attribute` target. For example, a declaring SDK can expose:

```toml
[project.entry-points."scitex_dev.hierarchy"]
scitex-sdk = "scitex_sdk.hierarchy:get_hierarchy_nodes"
```

A declaration is metadata, not proof that its target exists, is callable, or is
implemented by files in the owning distribution. The declaration-name check
binds the catalog key to its recorded owner; invocation-time code ownership
and SDK record/tree validation remain separate work. Extras syntax and calls
in targets are not accepted by this contract.

The catalog preserves `name`, `target`, `distribution`, `version` and `summary`
from the shared `ProviderMetadata` record. Missing versions remain unknown
(`null` in JSON). Rows sort by declaration metadata, not hierarchy indices.
Duplicate owner declarations, aliases that differ from the canonical owner,
and malformed targets fail loudly. Validation covers the complete selected
metadata search before optional package filtering, so filtering cannot hide an
invalid competing declaration.

```bash
scitex-dev hierarchy list --package scitex-sdk --json
scitex-dev --json hierarchy list
scitex-dev hierarchy list --path /path/to/owned/site-packages --json
```

`--path` is repeatable and limits installed-metadata discovery. It must identify
existing directories; it does not add Python import paths or enable packages.
An empty catalog is `[]` in JSON or an explicitly metadata-only text summary.
It does not cause registry fallback, synthetic package declarations or a claim
that the SciTeX root/tree is complete. Config-based host admission, activation
and permission decisions are not applied by this metadata observer.

The Python API is `scitex_dev.list_hierarchy_providers(package=None, path=None)`
(or `scitex_dev.hierarchy_providers.list_hierarchy_providers`). It returns an
immutable tuple of shared `ProviderMetadata` rows. Explicit `path=[]` searches
nothing. Package filters accept standard distribution-name normalization.
Invalid declarations or package identities raise `ValueError`; the CLI reports
those as failures. No SDK installation or SDK import is required for discovery.

The implementation lives in
[`hierarchy_providers`](../src/scitex_dev/hierarchy_providers/__init__.py) and
[the CLI adapter](../src/scitex_dev/_cli/_hierarchy.py). Real dist-info, imported
provider refusal and catalog behavior are covered by
[the provider tests](../tests/scitex_dev/hierarchy_providers/test___init__.py);
[CLI tests](../tests/scitex_dev/_cli/test__hierarchy.py) exercise the same catalog,
JSON inheritance and error exits. Installed provider discovery is distinct from
SDK-owned record validation, umbrella-owned root/layer declarations, other leaf
allocations, Docs ordering, global search, live availability and access policy.
