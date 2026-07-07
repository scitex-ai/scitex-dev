---
description: |
  [TOPIC] Interface Cli Dev Subgroup
  [DETAILS] SciTeX CLI developer-command placement — per-package `dev` noun group for developer/maintainer commands (list-python-apis, introspect, app/pkg scaffolds, audit hooks, docs-build, skills export); ecosystem-wide operations ALWAYS under `scitex dev ecosystem`.
tags: [scitex-general-interface-cli-dev-subgroup]
---

# §11. Developer commands — the `dev` subgroup & ecosystem placement

Operator-confirmed 2026-07-07. Two placement rules keep user-facing
help short and put every maintainer tool in the same place across all
packages.

## Per-package `dev` subgroup

Every package CLI groups **developer/maintainer-facing** commands under
a `dev` noun group:

```
<cli> dev list-python-apis [-v|-vv|-vvv] [--json]
<cli> dev introspect ...
<cli> dev scaffold-app <name>          # app/pkg scaffolds
<cli> dev docs-build
<cli> dev skills-export                # or: dev skills export
```

### What goes in `dev` (confirmed classification)

| In `dev` (developer-facing)                       | NOT in `dev` (user-facing, stays top-level)          |
|----------------------------------------------------|--------------------------------------------------------|
| `list-python-apis`                                 | `completion` group (§1b [04_exceptions.md](04_exceptions.md)) |
| `introspect` verbs                                 | `benchmark`                                            |
| app / pkg scaffold verbs                           | research-project / research-template scaffolds         |
| audit hooks                                        | `mcp` group                                            |
| `docs-build`                                       | `notification` commands                                |
| skills export / sync (maintainer verbs)            | domain verbs (the package's actual purpose)            |

- Tie-break: commands an **end user** runs to *use* the package never
  go under `dev`; commands only a package **developer/maintainer** runs
  always do.
- Scaffolds split by audience: creating a *research project* is a user
  action; creating an *app or package skeleton* is developer work.
- The `dev` group renders under the `Introspection` help category
  (§4a [10a_command-categories.md](10a_command-categories.md)).
- Migration: existing top-level mounts (`<cli> list-python-apis`, …)
  become Phase W warn-forward aliases for the `dev`-nested form
  (§5 [11_deprecation.md](11_deprecation.md)).

## Ecosystem-wide operations — ALWAYS `scitex dev ecosystem`

Ecosystem-wide operations (versions across packages, fleet sync,
registry management, fleet-wide audits) live in **exactly one place**:
scitex-dev's `ecosystem` group, mounted on the umbrella as

```
scitex dev ecosystem <verb> ...        # e.g. scitex dev ecosystem audit-cli --all
```

- `scitex dev ecosystem` is the **single aggregate/management point**.
- **Nothing ecosystem-wide mounts on any other package CLI.** A package
  CLI speaks only for its own package; if a command reasons about
  sibling packages, it belongs under `scitex dev ecosystem`.

## Rationale

- A user running `<cli> --help` sees the domain surface, not the
  maintainer plumbing — the `dev` group folds ~6 commands into one row.
- One fixed location for maintainer tools means an agent auditing any
  package knows to look at `<cli> dev` — no per-package hunting.
- One aggregate point prevents the drift where three packages each grow
  a half-featured `versions`/`sync-all` command.
