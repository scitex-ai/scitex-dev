---
description: |
  [TOPIC] CI test environment rule
  [DETAILS] Three-point rule for fleet tests: machine-independent tests, apptainer execution, spacious storage. Use when writing or reviewing tests, or when diagnosing red/green-by-host CI verdicts. Operator doctrine 2026-09-29.
tags: [scitex-dev-ci-test-environment]
---

# CI test environment — the three-point rule

Status: **fleet law** (掟). Operator doctrine 2026-09-29: at fleet
scale the test environment is standardised, not assumed.

1. **Tests are machine-independent.** A test asserts its code, never
   facts about the machine: no assumed paths, mounts, interpreter
   builds, installed system packages, or free space. Environment facts
   the code genuinely needs (baked SIF contents) are asserted by
   environment tests, marked as such, and never mixed into unit suites.
2. **Tests run in apptainer.** CI executes the suite inside the shared
   SIF (`ci-cpu.sif`), never on the bare runner. A green run outside
   the SIF predicts nothing about a green run inside it.
3. **Tests run on spacious storage.** Job scratch, SIF staging, and
   runner workspaces live on scratch, never on root. A full root disk
   with free scratch is always a placement bug (see
   `37_host-disk-placement.md`), and a test that fails for lack of
   space is a placement failure, not a code verdict.

Red/green-by-host is therefore always one of: a rule-1 violation (fix
the test), a rule-2 violation (run it in the SIF), or a rule-3
violation (move the storage). Buying hardware answers only rule 3.

**Preflight.** Check free space before starting and fail fast when
below threshold — a slow death mid-job (02's diag-write crash) is
strictly worse than an immediate refusal naming the full filesystem.
