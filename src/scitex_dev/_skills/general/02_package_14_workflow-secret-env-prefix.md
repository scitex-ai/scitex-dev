---
description: |
  [TOPIC] GitHub Actions secret + env-var naming convention (per-package prefix).
  [DETAILS] Per-project secrets and env vars referenced inside
  `.github/workflows/*.yml` MUST carry a `<PKG>_` prefix where `<PKG>` is the
  package's distribution name uppercased with hyphens converted to underscores
  (e.g. `newb` → `NEWB_`, `scitex-agent-container` → `SCITEX_AGENT_CONTAINER_`).
  A short exception list covers cross-cutting names that `scitex-dev creds
  rotate-all` deliberately targets (`CLAUDE_CODE_CREDENTIALS_JSON`), tool-pinned
  envs (`GH_TOKEN`, `GITHUB_TOKEN`), and third-party-named tokens
  (`CODECOV_TOKEN`, `GHCR_PAT`). Audited by PS-168.
tags: [scitex-general-package-workflow-secret-env-prefix]
---

# GitHub Actions — Per-Package Secret / Env-Var Prefix (SciTeX)

## Rule (PS-168)

Inside any `.github/workflows/*.yml`, every `${{ secrets.<NAME> }}` or
`${{ env.<NAME> }}` reference whose `<NAME>` is project-specific MUST use
the form

```
<PKG>_<UPPERCASE_NAME>
```

where `<PKG>` is the package's distribution name (the project name shown
in `pyproject.toml [project] name`) **uppercased** with hyphens replaced
by underscores. Examples:

| Package distribution         | Prefix                       | Example secret                              |
|------------------------------|------------------------------|---------------------------------------------|
| `newb`                       | `NEWB_`                      | `NEWB_CLAUDE_CODE_CREDENTIALS_JSON`         |
| `scitex-agent-container`     | `SCITEX_AGENT_CONTAINER_`    | `SCITEX_AGENT_CONTAINER_NAS_SSH_KEY`        |
| `scitex-dev`                 | `SCITEX_DEV_`                | `SCITEX_DEV_PYPI_API_TOKEN`                 |
| `socialia`                   | `SOCIALIA_`                  | `SOCIALIA_OPENAI_API_KEY`                   |

Workflow YAML usage:

```yaml
# YES — prefixed, distinguishable from cross-cutting names
env:
  CLAUDE_CODE_CREDENTIALS_JSON: ${{ secrets.NEWB_CLAUDE_CODE_CREDENTIALS_JSON }}

# NO — un-prefixed; rotate-all can't tell whether this is the shared
# ecosystem credential or a per-project copy with the same surface name
env:
  CLAUDE_CODE_CREDENTIALS_JSON: ${{ secrets.CLAUDE_CREDENTIALS_JSON }}
```

## Why

`scitex-dev creds rotate-all` rotates a fixed set of *cross-cutting*
secret names (e.g. `CLAUDE_CODE_CREDENTIALS_JSON`) across every
ecosystem package's GitHub repo. If a per-project secret picks an
un-prefixed name like `CLAUDE_CREDENTIALS_JSON`, rotate-all has no way
to know whether to overwrite it (cross-cutting?) or leave it alone
(project-specific?). The historical behaviour was to skip — silently —
which broke `newb`'s CI when its hand-rolled `CLAUDE_CREDENTIALS_JSON`
went stale while the canonically-named ecosystem secret was rotated
into freshness around it (newb PR #1, 2026-05-18).

The fix is the prefix discipline: anything starting with `<PKG>_` is
*by construction* not the rotate-all target, and the unprefixed names
in the exception list below ARE the rotate-all targets. The two sets
no longer overlap; rotate-all and per-package CI stop stepping on each
other.

## Exception list (un-prefixed names that are NOT violations)

These names are deliberately ecosystem-wide or tool-pinned and therefore
allowed without a `<PKG>_` prefix:

| Name                          | Reason                                                                     |
|-------------------------------|----------------------------------------------------------------------------|
| `CLAUDE_CODE_CREDENTIALS_JSON`| The `creds rotate-all` ecosystem-wide target.                              |
| `GH_TOKEN`                    | Honored by the `gh` CLI as the GitHub auth token (tool-pinned name).       |
| `GITHUB_TOKEN`                | Injected by GitHub Actions itself; cannot be renamed.                      |
| `CODECOV_TOKEN`               | Codecov's third-party-pinned token name.                                   |
| `GHCR_PAT`                    | GitHub Container Registry pull/push PAT — common cross-package convention. |
| `NPM_TOKEN`                   | npm publish convention.                                                    |
| `PYPI_API_TOKEN`              | Reserved name for PyPI publish (we use OIDC, but legacy workflows exist).  |
| `ACTIONS_RUNNER_DEBUG`        | GitHub Actions diagnostic toggle.                                          |
| `ACTIONS_STEP_DEBUG`          | GitHub Actions diagnostic toggle.                                          |

If a future cross-cutting credential joins the rotate-all corpus, add
its bare name here and update the auditor's exception list in the same
PR.

## Audit (PS-168)

`PS-168` (severity `E`) scans every `.github/workflows/*.yml` under the
repo. For each `${{ secrets.<NAME> }}` reference it checks:

1. `<NAME>` is NOT in the exception list above, AND
2. `<NAME>` does NOT start with the package's `<PKG>_` prefix.

When both are true, the auditor reports:

```
ERRO: <pkg>: [PS-168 §1 secret-env-prefix-missing] <relpath>:<lineno>:
      secret name "<NAME>" should be prefixed "<PKG>_<NAME>"
```

The same check is applied to `${{ env.<NAME> }}` references when the
right-hand side resolves to `secrets.<...>` — a workflow that stuffs a
secret through `env:` doesn't bypass the rule.

## Migration

For a package with a non-prefixed secret already in flight:

```bash
# 1. Add the prefixed secret to the GitHub repo's Settings → Secrets.
gh secret set NEWB_CLAUDE_CODE_CREDENTIALS_JSON < /path/to/creds.json

# 2. Update the workflow:
sed -i 's/secrets\.CLAUDE_CREDENTIALS_JSON/secrets.NEWB_CLAUDE_CODE_CREDENTIALS_JSON/g' \
    .github/workflows/*.yml

# 3. Delete the legacy secret.
gh secret delete CLAUDE_CREDENTIALS_JSON

# 4. Verify rotate-all now sees the package:
scitex-dev creds rotate-all --dry-run
```

## See also

- `01_ecosystem_04_environment-variables.md` — runtime env-var naming
  (this leaf's sibling for `[tool.scitex_dev] env` keys).
- `02_package_07_github-actions.md` — canonical workflow patterns.
- `02_package_12_workflows-naming.md` — workflow filename grammar (PS-164).
- `02_package_07b_workflow-presence.md` — required workflow baseline (PS-165).
