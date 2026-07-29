---
description: |
  [TOPIC] GitHub Actions workflow presence.
  [DETAILS] Required baseline of workflow files every SciTeX package must
  ship. Audited by PS-165 (severity W during adoption). Companion to
  02_package/07_github-actions.md (canonical content) and
  02_package/12_workflows-naming.md (filename grammar).
tags: [scitex-general-package-workflow-presence]
---

# Workflow Presence (SciTeX)

## Required baseline (every package)

| Workflow                                               | Filename pattern (PS-164)                          | Why                                       |
|--------------------------------------------------------|----------------------------------------------------|-------------------------------------------|
| CLA Assistant                                          | `cla.yml`                                          | Pinned by the CLA bot.                    |
| pytest matrix                                          | `pytest-*-on-*.yml`                                | The unit-test gate.                       |
| Import smoke                                           | `import-smoke-*-on-*.yml`                          | `pip install` + `python -c "import X"`.   |
| PyPI publish on tag                                    | `pypi-publish-*-on-tag.yml`                        | Trusted-publisher OIDC release.           |
| scitex-dev quality audit                               | `scitex-dev-quality-audit-on-*.yml`                | Ecosystem-wide audit-all gate.            |
| Sync main → release tag                                | `sync-main-to-release-tag-on-push.yml`             | Branch-protection-friendly release shim.  |
| RTD Sphinx build *(only when `docs/` ships)*           | `rtd-sphinx-build-on-*.yml`                        | RTD docs build sanity.                    |

The RTD requirement is gated on the presence of a `docs/` tree (with
`conf.py` at `docs/conf.py` or `docs/source/conf.py`). Packages without
docs don't ship the build workflow.

Note: the `tests/smoke/` and `tests/e2e/` *pytest* layers (PS-211 / PS-212)
are a separate concern — they live inside the test suite, and are opted out
of per-repo with `[tool.scitex_dev] no_cli` / `no_e2e`.

## Retired: the per-package `category` axis

PS-165 used to vary its required set on a `[tool.scitex_dev] category`
declaration (`library` / `cli-tool` / `infrastructure`, defaulting to
`library`), with `cli-tool` additionally requiring a runtime CLI smoke
workflow (`sdk-runtime-smoke-on-*.yml` / `cli-smoke-on-*.yml`). A census
of the ecosystem found **zero** repos declaring that key, so the branch
never fired — every package was audited against the baseline regardless.
The axis has been removed; do not declare it.

This says nothing about two other, live classification channels:
`project-type` in `<repo>/.scitex/dev/config.yaml`, and the `category`
field on the hardcoded `scitex_dev.ECOSYSTEM` registry (its own
`umbrella` / `external-lib` / `dataset` vocabulary).

## Audit (PS-165)

`PS-165` (severity `W` during adoption) verifies every required filename
pattern matches at least one file under `.github/workflows/`. Emits one
violation per missing workflow.

Promote to E once the ecosystem has converged on the baseline.
