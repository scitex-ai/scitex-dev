---
description: |
  [TOPIC] Release + Exact-Pin Doctrine (aggressive-publish, no-approval)
  [DETAILS] The operator's standing release/versioning doctrine (2026-07-06), stated authoritatively so it can be referenced from the constitution. Two rules set the DEFAULT posture across the fleet: (1) publish scitex packages aggressively and often WITHOUT an approval gate — the release flow runs autonomously (develop→main→tag→PyPI) and a release is not disruptive, so fix-forward on any regression instead of hesitating; (2) the scitex-python umbrella is the SINGLE deterministic pin-point — it exact-pins (`==`) every scitex member package, so leaf packages may keep `>=` floors (the umbrella constrains resolution tightest-wins in any env that includes it: the SIF, fleet envs). Concentrating the pins at the umbrella gives determinism without the resolution conflicts blanket per-leaf exact-pinning would cause; volatile third-party deps (fastmcp) are exact-pinned at the umbrella/deployment layer on the same principle. Covers how to apply both, how scitex-dev (the version overseer) enforces the umbrella `==` rule via a CLI/audit check + pre-commit/CI + the container hook-set, and how the doctrine sits alongside the existing dependency-pinning guidance. Read before releasing any scitex-* package or editing the umbrella's member pins.
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

- The release flow runs **autonomously**: develop → main → tag → PyPI,
  no human in the loop for scitex-internal packages.
- A release is **not disruptive** — publishing a wheel does not drop
  sessions or break consumers who have not bumped; it just makes the
  new version available to whoever pulls it.
- **Fix-forward, always.** If a release has a problem, cut a bugfix
  release *immediately* (patch bump, same flow) rather than yanking,
  reverting, or pausing the cadence. A regression is one more release
  away from fixed — never a reason to stop shipping.
- **The autonomy is GATED, not unconditional.** "No approval gate"
  means no *operator* gate — it does NOT mean no gate. CI must be
  **green**, and the repo's release ritual must pass: a CHANGELOG
  entry, the version bump, and the packaging / import gates. Those
  honest, deterministic gates — not a human ask — are what make a bad
  publish a cheap yank instead of a silent breakage; that reversibility
  is precisely what licenses publishing without asking. Keep the
  import/packaging gates honest and they carry the safety the operator
  gate used to.

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

**Autonomous release flow** (no approval gate) — run without a sign-off:

```bash
# develop green → open + auto-merge release PR → tag → PyPI on the v* tag
gh pr create --base main --head develop --title "Release X.Y.Z — <summary>"
gh pr merge <PR#> --merge --auto
git -C <repo> tag -a vX.Y.Z origin/main -m "vX.Y.Z"
git -C <repo> push origin vX.Y.Z        # publish-pypi.yml fires on the tag
```

Mechanics: [03_release-automation.md](03_release-automation.md). The
*doctrine* is that you run this without an approval gate on
scitex-internal packages, and **fix-forward** on any regression (patch
bump → same flow; no yank, no retag).

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
