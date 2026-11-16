---
description: |
  [TOPIC] Autonomous release and pin doctrine
  [DETAILS] Standing authorized release cadence with exact-head checks, leaf-owned publication stages and immutable tags. Library metadata (umbrella and leaves) declares minimum-compatible `>=` floors; exact versions live only in experiment/deployment lock files (scitex-python#393).
tags: [scitex-general-development-release-pin-doctrine]
---

# Release + Pin Doctrine

Operator mandate, **2026-07-06**. Two standing rules that set the
DEFAULT posture for the fleet: **publish aggressively, with no approval
gate**, and **declare compatibility floors in library metadata while
exact versions live in lock files** (§2, revised 2026-11-16). Both serve one goal —
*velocity* across a fleet of packages developed in parallel across many
hosts and agents. This is the authoritative,
**constitution-referenceable** statement of the policy.

Companion to [13_version-drift-management.md](13_version-drift-management.md)
(the drift lifecycle this doctrine's publish cadence feeds),
[03_release-automation.md](03_release-automation.md) (the release
commands), and
[../01_ecosystem/02_dependency-and-version-pinning.md](../01_ecosystem/02_dependency-and-version-pinning.md)
(dependency hygiene — this doctrine sits alongside it; see §5).

## 1. Aggressive publish — no approval gate

**Release scitex packages FREELY and OFTEN.** Do NOT gate a release on
operator approval. The time spent hesitating or asking "should I
publish this?" is pure waste — it stalls every downstream host,
container, and agent waiting on the change.

- Within the authorized scope, the release flow runs **autonomously**
  through ordinary source promotion and the leaf's actual validation and
  publication stages. Do not request confirmation already granted.
- Publication makes an artifact available; installed profiles and live
  services are separate adoption steps. Qualify the intended dependency
  cohort before updating either one.
- **Fix-forward.** Correct released source with a new version and normal
  checks. Use the leaf's rollback procedure if a deployed profile needs to
  return to a qualified version; never move a published tag.
- **The autonomy is GATED, not unconditional.** "No approval gate"
  means no *operator* gate — it does NOT mean no gate. CI must be
  **green**, and the repo's release ritual must pass: a CHANGELOG
  entry, the version bump, and the packaging / import gates. Those
  honest, deterministic gates remain mandatory under autonomous release.
  Publication is not reversible by deleting or replacing artifacts; a fix
  uses a new version, and service rollback follows the leaf's procedure.

**Re-ratified 2026-07-08 as a UNIVERSAL fleet rule** — the operator
directed it be shared with every agent as a universal rule (普遍ルール):

> 「リリースは私の確認不要、むしろ聞かないでくださいレベルで、どんどん
>   リリースして…これを普遍的なルールとしてみんなで共有してください」
>
> — releases do not need my confirmation; if anything, please do NOT ask.
>   Release freely, and share this with everyone as a universal rule.

It applies to every
agent and every scitex repo, and is mirrored in the constitution's
delivery section so it loads for all agents, not just those who read
this skill.

**Rationale (operator).** scitex packages are *actively developed*;
the goal is velocity across hosts and agents. A hesitation gate
optimizes against a risk (a bad release) that fix-forward already
handles cheaply — at the cost of the thing that actually matters:
getting changes live everywhere, fast.

## 2. Floors in the umbrella, exact versions in lock files

**Superseded 2026-11-16** ([scitex-python#393](https://github.com/scitex-ai/scitex-python/pull/393)): the umbrella no
longer exact-pins its members.

- **Library metadata = minimum-compatible floors.** The umbrella
  (`scitex-python`) and every leaf declare SciTeX members with `>=`
  floors: the oldest version whose interface the code actually uses.
- **Lock files = exact versions.** Reproducibility of a specific
  experiment, deployment, SIF image or fleet profile comes from that
  consumer's lock file (`uv.lock`, `requirements.lock`, the deployment
  pin file), never from `pyproject.toml` dependency metadata.

Why the exact-pin rule (2026-07-06) was dropped:

- An exact `==` pin in the umbrella is a *ceiling* as well as a floor.
  Installing the umbrella next to a newer develop build of a member
  **silently downgraded** that member to the pinned release.
- It made develop components uninstallable with the umbrella: a develop
  `scitex-session` that needed a newer peer than the umbrella's `==`
  pin could not resolve at all.
- Library metadata states compatibility; determinism is a property of a
  concrete environment, which is exactly what a lock file records.
- The same applies to volatile **third-party** deps (`fastmcp`, ...):
  give a compatibility floor (plus a documented upper bound only when a
  known break exists) in metadata, and the exact version in the
  deployment lock file.

## 3. How to apply

**Umbrella and leaves — `>=` floors:**

```toml
# scitex-python/pyproject.toml (and any leaf) — compatibility floors
dependencies = [
    "scitex-io>=0.4.7",
    "scitex-stats>=0.5.2",
    "fastmcp>=2.3.0",
]
```

**Experiment / deployment — exact versions in the lock file:**

```bash
uv lock                     # or: uv pip compile pyproject.toml -o requirements.lock
uv sync --frozen            # install exactly what the lock records
```

When you cut a new member version, raise the umbrella's floor only if
the umbrella (or its re-exports) now relies on the new interface, then
refresh the lock files of the experiments/deployments that should adopt
it ([13_version-drift-management.md](13_version-drift-management.md) §3).
A leaf likewise raises its floor only when it uses a new API.

**Authorized autonomous release flow.** Follow the user's current release
scope and existing session authorization; do not infer publication permission
from green CI alone or request confirmation already granted.

Review every check at the exact release-PR head, including consent and security
outcomes. Merge normally with the reviewed head guard; do not enable auto-merge
or bypass a failed check. Tag only the accepted main commit, using an unused
canonical version and an explicit single-tag push.

Inspect the leaf's workflow before publication. A tag may trigger only
validation: Dev publishes through a separate protected-main workflow dispatch.
Use [18_end-to-end-release-flow.md](18_end-to-end-release-flow.md) and the leaf's
own instructions rather than a generic tag-to-PyPI recipe. Keep source,
artifacts, installed interfaces and live adoption separate. Correct a released
regression by qualifying a new version, never by moving a published tag.

## 4. Enforcement — scitex-dev is the version overseer

`scitex-dev ecosystem audit-umbrella-pins` (PS-170) accepts `>=` floors
on umbrella members. It still checks any remaining explicit `==` pin
against PyPI latest and reports drift (warn by default, `--strict` in a
pre-publish gate), because a stale `==` is a real bug class. Do not add
checks that *require* `==` on umbrella members, and do not reintroduce
`==` member pins in the umbrella's `pyproject.toml`.

## 5. Relationship to existing pinning guidance

This doctrine is **consistent** with
[../01_ecosystem/02_dependency-and-version-pinning.md](../01_ecosystem/02_dependency-and-version-pinning.md):
every package, umbrella included, declares compatible `>=` floors;
exact versions live only in experiment/deployment lock files. The
2026-07-06 "umbrella exact-pins every member" rule is retired
([scitex-python#393](https://github.com/scitex-ai/scitex-python/pull/393)).

Likewise, §1's aggressive-publish rule sets the **default posture** for
scitex-internal packages, superseding a blanket "never auto-release
without per-release approval" stance for this fleet. The one-way-upload
caution in [03_release-automation.md](03_release-automation.md) still
applies to *external* packages, where no fix-forward safety net exists.

## Related

- [13_version-drift-management.md](13_version-drift-management.md) — the
  8-layer drift lifecycle this doctrine's publish cadence feeds.
- [03_release-automation.md](03_release-automation.md) — the release
  commands (the autonomous flow's mechanics).
- [../01_ecosystem/02_dependency-and-version-pinning.md](../01_ecosystem/02_dependency-and-version-pinning.md)
  — dependency hygiene; floors everywhere, exact versions in lock files.
- **Constitution** — this skill is the authoritative,
  constitution-referenceable statement of the release + pin
  doctrine.
