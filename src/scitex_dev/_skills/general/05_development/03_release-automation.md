---
description: |
  [TOPIC] Release inventory and automation boundaries
  [DETAILS] Inspect ecosystem versions through the actual CLI, public Python API and registered MCP tools. Version reports are diagnostic snapshots, not release acceptance. Follow standing authorization, leaf-owned publication and separate host rollout checks.
tags: [scitex-general-development-release-automation]
---

# Release inventory and automation boundaries

Dev supplies ecosystem inventory and reconciliation tools. The package being
released owns its version source, test profile, publication workflow and rollout.
Start with [version control](01_version-control.md), then follow the
[release flow](18_end-to-end-release-flow.md). Existing scoped user authorization
persists; green CI alone does not supply missing publication authority.

## Inspect the inventory

Prefer the umbrella CLI when installed. Standalone `scitex-dev` is the bootstrap
route; check its actual help when the umbrella is unavailable.

```bash
scitex dev ecosystem list --json
scitex dev ecosystem list --package scitex-dev --versions --json
scitex dev ecosystem validate-versions --help
scitex dev docs validate --path /owned/package --document README.md --json
```

`ecosystem list` defaults to the roster. `--versions` adds observations from
local source, installed distributions, Git and PyPI. These observations may be
unavailable or inconsistent; inspect the reported issues and install provenance.
A dynamic version source such as setuptools-scm need not have a static
`project.version` in `pyproject.toml`.

`ecosystem validate-versions` can contact configured fleet hosts. Its ordinary
mode reports observations, `--dry-run` previews reconciliation and `--apply`
executes it. Inspect the selected hosts and package scope before invoking it.
This guide does not request a fleet sweep, editable reinstall or automatic sync.
The deprecated `fix-mismatches` and `packages` CLI routes are not the current
release procedure.

## Public Python API

Use the public exports from `scitex_dev`, not the removed
`scitex_dev.versions` or `scitex_dev.fix` module paths:

```python
from scitex_dev import get_mismatches, list_versions

versions = list_versions(packages=["scitex-dev"])
mismatches = get_mismatches(packages=["scitex-dev"])
for package, observation in versions.items():
    print(package, observation["status"], observation.get("issues", []))
```

These functions collect observations; they are not purely offline operations.
`packages=None` selects the ecosystem roster. A `commits_since_tag` count is
review input, not proof that every package needs a bump or that it is safe to
publish. Review change scope and the leaf's actual version strategy.

The public `fix_mismatches` function remains for backward compatibility. Its
`confirm=False` default is a preview; `confirm=True` can install or sync packages
locally and remotely. Do not substitute it for immutable-tag qualification or
use a broad reconciliation to overwrite unrelated host work.

Implementation: `scitex_dev/_release/versions.py`, `_release/fix.py` and public
exports in `scitex_dev/__init__.py`.

## MCP discovery

Query the connected server's tool list; the client may add its own namespace.
The standalone Dev server registers these relevant names in `_mcp/_server.py`:

| Tool | Scope |
|---|---|
| `dev_ecosystem_list` | Version observations for selected packages |
| `dev_config_show` | Resolved Dev configuration |
| `dev_ecosystem_fix_mismatches` | Legacy reconciliation; `dry_run=True` by default |
| `dev_ecosystem_sync_local` | Editable installation; `confirm=False` by default |
| `dev_ecosystem_sync_remote` | Remote synchronization; `confirm=False` by default |

A tool listed in source need not be advertised by every client configuration.
Listing a mutation tool does not authorize invoking it. Keep source registration,
actual server discovery and execution results as separate evidence.

## Workflow integrity checks

The normal project auditor checks local GitHub workflow shell steps:

- **PS-235** reports literal `pip`, `python -m pip`, or `uv pip` install chains
  that select a different local extras profile after `||`. Use one explicitly
  selected profile and stop when it fails. A successful smaller install does
  not qualify the originally requested profile.
- **PS-236** reports literal `gh pr merge --admin` commands. Keep protection
  enabled and leave a PR open until normal checks and reviews allow merging.

These checks inspect literal commands in Bash-compatible `run` steps. Quoted
examples, comments and heredoc data are not executed commands. Indirect scripts,
generated commands and reusable workflow implementations need their own review;
zero findings here are not complete release acceptance.

From the Dev checkout, an umbrella installation can select these checks with:

```bash
scitex dev ecosystem audit-project scitex-dev --path . --rule PS-235 --rule PS-236
```

Implementation: `_cli/audit/_project/_check_workflow_integrity.py`, registered
through the existing project-audit dispatcher and rule registry.

## Qualify and publish

1. Inspect the requested package, source state, published versions and unused
   canonical version. Preserve dirty checkouts and unrelated work.
2. Use an owned worktree to integrate accepted source. Review all checks at the
   exact PR head, including consent and security outcomes; required checks alone
   are insufficient. Merge normally with a reviewed-head guard, without auto-merge.
3. Follow the leaf's actual workflow. Dev uses setuptools-scm, tag-driven native
   release validation and a separate protected-main publication dispatch; see
   its [source-owned procedure](../../scitex-dev/18_full-update.md).
4. Verify whole wheel/sdist identities, dependency-compatible installation and
   documented interfaces. Treat generated docs, source skills, exported skills
   and served pages as separate artifacts.
5. Roll out only qualified artifacts through the leaf's deployment procedure,
   preserving user data and a tested rollback. Verify actual installed and
   running versions separately from the repository tag.

Do not force-push or move published tags, replace failed checks with synthetic
verdicts, relax tests or presume a tag event publishes to PyPI. Preserve failures
and report unavailable coverage. See
[release pipeline gotchas](19_release-pipeline-gotchas.md) and
[documentation drift](22_documentation-drift.md).
