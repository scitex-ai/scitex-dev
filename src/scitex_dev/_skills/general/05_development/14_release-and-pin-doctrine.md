---
description: |
  [TOPIC] Autonomous release and exact-pin doctrine
  [DETAILS] Standing authorized release cadence with exact-head checks, leaf-owned publication stages and immutable tags. The umbrella exact-pins SciTeX members while leaves retain minimum floors; Dev enforces the pin contract.
tags: [scitex-general-development-release-pin-doctrine]
---

# Release + Exact-Pin Doctrine

Operator mandate, **2026-07-06**. Two standing rules that set the
DEFAULT posture for the fleet: **publish aggressively, with no approval
gate**, and **exact-pin the scitex members at the scitex-python
umbrella** (the single deterministic pin-point). Both serve one goal —
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

## 2. Exact-pin at the umbrella — the single deterministic pin-point

**The scitex-python umbrella exact-pins (`==`) every scitex member
package. Leaf packages MAY keep `>=` floors for their scitex-to-scitex
deps.** The umbrella is the one place the pin set is made deterministic;
concentrating the pins there — rather than exact-pinning every leaf — is
deliberate.

Why this shape:

- scitex packages are actively-developed and *unstable* (APIs move
  release-to-release), so the resolved version set must be
  deterministic. But exact-pinning *every leaf's* scitex deps causes
  resolution **conflicts** the moment two leaves pin divergent versions.
- Instead, pin at ONE point: `scitex-python==X` exact-pins all members.
  In any environment that installs the umbrella, pip's tightest-wins
  resolution **forces** every member to the umbrella's pinned version —
  so leaves stay loose (`>=`) and the resolved set is still
  deterministic.
- Determinism holds **wherever the umbrella is present** — the SIF
  image, every fleet env. Caveat: a leaf installed *standalone* (no
  umbrella) can resolve to latest; that is acceptable, because the
  fleet / SIF always installs the umbrella.
- Same principle for volatile **third-party** deps (`fastmcp`, …):
  exact-pin them at the umbrella / deployment layer, not scattered
  across leaves.

## 3. How to apply

**Umbrella (`scitex-python`) — the pin-point: `==` every member:**

```toml
# scitex-python/pyproject.toml — exact-pin every scitex member
dependencies = [
    "scitex-io==0.4.7",
    "scitex-stats==0.5.2",
    "fastmcp==2.3.0",          # volatile 3rd-party — exact-pin here too
]
```

**Leaf package — `>=` floors are fine** (the umbrella tightens them in
any env that includes it):

```toml
# a leaf pyproject.toml — minimum-pin scitex deps; umbrella constrains them
dependencies = [
    "scitex-io>=0.4.0",
    "numpy>=1.21.0",
]
```

When you cut a new scitex member version, bump its `==` pin in the
umbrella (part of the coordinated wave,
[13_version-drift-management.md](13_version-drift-management.md) §3
step 4). A leaf only raises its `>=` floor when it actually relies on a
new API.

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

The enforced check is: **scitex-python's dependency list uses `==` for
every scitex member.** scitex-dev owns fleet version consistency
([13_version-drift-management.md](13_version-drift-management.md)), so:

- **CLI / audit rule.** `scitex-dev ecosystem audit-umbrella-pins
  --strict` (PS-170) checks the umbrella's `==` member pins in the
  release-pipeline pre-publish gate. The doctrine hardens it to
  *require* `==` on every member — reversing the 2026-05-28 relaxation
  that also accepted `>=` on umbrella peers.
- **Pre-commit / CI check.** The audit runs on every push to
  scitex-python, so a member that regresses to a `>=` floor is caught
  before merge.
- **Container hook-set.** scitex-agent-container folds "the umbrella dep
  list is fully `==`-pinned" into the container's hook-set, so the
  check runs at write time across every container, not just in CI.

## 5. Relationship to existing pinning guidance

This doctrine is **consistent** with
[../01_ecosystem/02_dependency-and-version-pinning.md](../01_ecosystem/02_dependency-and-version-pinning.md)
and adds one rule on top:

- That skill's "leaves use `>=` minima, avoid `==`" rule stands
  unchanged — leaf packages keep `>=` for both scitex and third-party
  deps.
- **New:** the umbrella is the exception and the pin-point — it
  `==`-pins every member. This supersedes, for the umbrella's member
  pins only, the 2026-05-28 PS-170 relaxation that accepted `>=` peers.

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
  — dependency hygiene; §5 places this doctrine's umbrella-`==` rule
  alongside the leaf `>=` convention.
- **Constitution** — this skill is the authoritative,
  constitution-referenceable statement of the release + exact-pin
  doctrine.
