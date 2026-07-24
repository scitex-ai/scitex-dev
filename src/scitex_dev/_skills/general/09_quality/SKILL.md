---
description: |
  [TOPIC] Ecosystem Quality And Failure Playbook
  [DETAILS] Periodic cross-package quality concerns for ecosystem maintainers — the crash-early/crash-loud fail-fast discipline (surface errors immediately and loudly, no silent fallbacks), the severity-tagged triage table for recurring ecosystem failures and its two recipe leaves (packaging/release failures where the published artifact is wrong, and compat/refactor drift where what the code references changed), the strategic /speak-and-call runbook with an append-only log plus its release-gate probes, the verification doctrine by claim type (how a check fails without going red — the six-state search taxonomy, absence/causal/content/artifact/peer rules), and its companion on controls that license nothing (vacuous, inert, mispositioned, degrade-branch masking, status words). Use when something feels off across packages, when triaging a recurring failure, before reporting a zero or a green, or when running a periodic ecosystem quality sweep.
tags: [scitex-general-quality-index]
---

# Ecosystem Quality (SciTeX) — Index

Periodic cross-package audits — run when something feels off. Audience:
ecosystem maintainers ([../SKILL.md](../SKILL.md)).

## Sections

0. [00_crash-early-crash-loud.md](00_crash-early-crash-loud.md) — Fail-fast discipline: surface errors immediately and loudly, no silent fallbacks

### Failure playbook — triage table, then the recipe by class

1. [01_failure-playbook.md](01_failure-playbook.md) — Severity-tagged symptom→fix triage table and triage order; routes to the two recipe leaves below
2. [05_packaging-and-release-failures.md](05_packaging-and-release-failures.md) — §3–§4, §6–§8, §10–§11: the repo is right and the published artifact is wrong (PyPI publisher, wheel drift, extras, undeclared transitive deps, license metadata)
3. [06_compat-and-refactor-drift.md](06_compat-and-refactor-drift.md) — §5, §9, §12: nothing was edited, but what the code references changed (numpy 2 / pandas, optional deps, path migration, CLI rename)

### Periodic quality pass — what to observe, then what it authorises

4. [02_checklist.md](02_checklist.md) — §0–§10: the strategic /speak-and-call runbook — scope gate, repo-level and content-level audits, automation audits, append-only log
5. [07_release-gate-probes.md](07_release-gate-probes.md) — §11–§19: response protocol, do-not-touch guard, and the standing release-blocking probes plus the ten release-gate questions

### Verification — trusting your own measurements

6. [03_verification-doctrine.md](03_verification-doctrine.md) — How a check fails without going red, by claim type: absence/causal/content/artifact/peer rules and the six-state search taxonomy
7. [04_verification-controls.md](04_verification-controls.md) — When the control itself licenses nothing: vacuous/inert/mispositioned/sampling controls, degrade-branch masking, status words, findings-as-cards
