---
description: |
  [TOPIC] Version observations
  [DETAILS] Inspect local source, installed provenance, Git and PyPI observations through current public helpers. Version status is diagnostic, not release acceptance. Legacy reconciliation is separate from publication and host deployment.
tags: [scitex-dev-versions]
---

# Version observations

## Read selected packages

```python
from scitex_dev import check_versions, get_mismatches, list_versions

versions = list_versions(packages=["scitex-dev"])
for package, observation in versions.items():
    print(package, observation["status"], observation.get("issues", []))

report = check_versions(packages=["scitex-dev"])
print(report["summary"])
mismatches = get_mismatches(packages=["scitex-dev"])
```

All three functions accept `packages: list[str] | None = None`. `None` selects the
bundled ecosystem roster. Collection can inspect configured checkouts and contact
PyPI; it is not a purely offline operation.

`list_versions` returns a dictionary keyed by package name. An observation can
include `local`, `git`, `remote`, `status` and `issues`; fields depend on source
availability. Installed provenance checks distinguish the effective version
from a raw metadata claim. Inspect fields such as `installed_metadata_claim`,
`install_kind` and `install_trustworthy` when present.

A dynamic version strategy need not declare a static `project.version`.
Missing information is not permission to invent a version or repair a tag.

| Status | Scope of the observation |
|---|---|
| `ok` | No mismatch detected by this version comparison |
| `mismatch` | Source/install/Git observations disagree or checkout state needs review |
| `unreleased` | A local version exceeds the observed PyPI version |
| `outdated` | A local version is behind the observed PyPI version |
| `unavailable` | Local source/install observations are unavailable |

`check_versions` adds summary counts. `get_mismatches` filters out `ok` and
`unavailable` entries. Neither an `ok` status nor an `unreleased` label establishes
CI acceptance, correct artifacts, contributor consent or publication readiness.

## Legacy reconciliation API

The public `fix_mismatches` function remains for backward compatibility. Its
selected parameters are a reference, not a call:

```text
fix_mismatches(hosts=None, packages=None, local=True, remote=True,
               confirm=False, config=None) -> dict
```

`confirm=False` previews; `confirm=True` can reinstall locally and synchronize
remote checkouts. A scoped local preview is:

```python
from scitex_dev import fix_mismatches

preview = fix_mismatches(
    packages=["scitex-dev"], local=True, remote=False, confirm=False
)
print(preview["detected"])
```

This function does not replace the leaf's publication workflow. Inspect the
selected scope and preserve unrelated work before any requested application.
Implementation: `_release/versions.py` and `_release/fix.py`.

## CLI

Prefer the umbrella route when its Dev adapter is installed:

```bash
scitex dev ecosystem list --package scitex-dev --versions --json
scitex dev ecosystem validate-versions --help
```

Standalone bootstrap: `scitex-dev ecosystem ...`. The legacy CLI names
`fix-mismatches` and `packages` do not define the current release procedure.
`validate-versions` can contact fleet hosts, and its `--apply` mode executes
reconciliation; inspect actual help and target scope before using it.

Follow [18_full-update.md](18_full-update.md) for qualified publication and
[19_release-deploy.md](19_release-deploy.md) for installed/runtime adoption.
