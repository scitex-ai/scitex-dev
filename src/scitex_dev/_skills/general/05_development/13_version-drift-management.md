---
description: |
  [TOPIC] Version-Drift Management across the distributed SciTeX fleet
  [DETAILS] The single hardest thing about developing the SciTeX ecosystem fast is keeping ONE package's version consistent across every layer it lives in: PyPI, GitHub (develop/main/tags), each host's per-project `.venv`, the agent container base image, each agent's overlay venv, CI, and every editable (`-e`) install. Drift in any layer silently ships stale or broken code and — worse — hides bugs (a broken CI feedback loop lets audit/test violations accumulate invisibly). This skill defines the drift matrix (what version lives where), the reconcile loop (`scitex-dev ecosystem validate-versions` and friends), the full release→propagate→rebuild→restart lifecycle, and the agent rebuild/restart protocol. Read this before any multi-package release wave, before asking "why is my change not live yet?", or when reconciling versions across hosts/containers/agents. Companion to 01_version-control.md (manual git flow) and 03_release-automation.md (release commands).
tags: [scitex-general-development-version-drift]
---

# Version-Drift Management

**Speed across the fleet is bottlenecked by version consistency.** One
scitex-* package's version lives in many places at once; when they
disagree, work silently runs against stale code and bugs hide. This
skill is the map of *where a version lives* and the *loop that
reconciles it*.

Companion to [01_version-control.md](01_version-control.md) (manual git
flow) and [03_release-automation.md](03_release-automation.md) (the
release commands themselves). This skill is about the **drift
dimension** those two don't fully cover: consistency across hosts,
containers, and agents.

## 1. The drift matrix — what version lives where

For any package `scitex-x`, its version is materialized independently in
**eight layers**. Each is a place drift can hide:

| # | Layer | Holds | How to read it | Reconcile with |
|---|-------|-------|----------------|----------------|
| 1 | **PyPI** | published release (external SSoT) | `pip index versions scitex-x` / `check_releases.py` | cut a release (§3) |
| 2 | **GitHub** | `develop` HEAD, `main` HEAD, tags | `git ls-remote --tags`, `gh run list` | promote develop→main→tag |
| 3 | **Host `ywata-note-win`** | per-project `.venv` editable installs | `ecosystem validate-versions -h ywata-note-win` | `validate-versions --apply` |
| 4 | **Host `spartan`** | CI-runner + compute venvs | `ecosystem validate-versions -h spartan` | `validate-versions --apply -h spartan` |
| 5 | **Container base image** | the apptainer image's baked venv | `sac`/image inspection (gap — see §5) | rebuild the image |
| 6 | **Agent overlay** | each agent's dedicated overlay venv | per-agent venv inspection (gap — §5) | redeploy+restart the agent |
| 7 | **CI** | what each workflow installs per run | the workflow yaml / run logs | pin/refresh in the workflow |
| 8 | **Editable installs** | `-e` → whatever the checkout currently is | `pip show -f scitex-x` → `Editable project location` | `git pull` + reinstall |

The **golden rule**: there is exactly **one source of truth per
question**. "What SHOULD the version be?" → `pyproject.toml` on the
target branch. "What IS published?" → PyPI. Every other layer is a
*cache* of one of those and must be reconciled toward it — never
hand-set independently.

## 2. Identify drift — the observe pass

Always **observe before you reconcile**. The backbone tool:

```bash
scitex-dev ecosystem validate-versions                 # Mode 1: observe (all hosts)
scitex-dev ecosystem validate-versions --json          # structured, for piping
scitex-dev ecosystem validate-versions -p scitex-io    # one package
scitex-dev ecosystem validate-versions -h spartan      # one host
```

Supporting probes:

```bash
scitex-dev ecosystem validate-sync                  # per-package develop-sha: local vs remote host(s)
~/.scitex/todo/check_releases.py                    # per-package pyproject-vs-PyPI (RELEASED/STALE/BEHIND/UNPUBLISHED)
scitex-dev ecosystem audit-umbrella-pins            # umbrella `==` pins vs PyPI latest
```

`check_releases.py` classifies each package:

| status | meaning | action |
|--------|---------|--------|
| `RELEASED` | pyproject == PyPI latest | none |
| `BEHIND` | pyproject > PyPI (unreleased commits) | **publish** (§3) |
| `STALE` | pyproject < PyPI (local behind PyPI) | pull/bump |
| `UNPUBLISHED` | not on PyPI yet | first publish |
| `DYNAMIC` | dynamic-version backend | classify manually |

## 3. Reconcile — the full lifecycle (release wave)

The end-to-end path that takes a merged change all the way to "live and
consistent on every layer." Do it **per package**, driven off the
`BEHIND` list from §2. Details of the individual commands live in
[03_release-automation.md](03_release-automation.md); this is the
ordering and the drift-closing steps 4–6 that release-automation stops
short of.

1. **Land on `develop` with GREEN CI.** Non-negotiable — see §4. A red
   develop poisons every downstream layer.
2. **Version bump** in `pyproject.toml`: `fix:` → patch, `feat:` →
   minor (constitution §4). Commit on develop.
3. **Publish**: promote `develop → main`, push tag `vX.Y.Z`. The
   `pypi-publish-and-github-release-on-tag` workflow publishes to PyPI +
   cuts the GitHub release. This closes layers **1, 2, 7**. (Layer 7:
   the C7 released-event producer emits a `released` card-event so the
   board reacts.)
4. **Propagate to hosts** (layers 3, 4, 8): once PyPI shows the new
   version, reconcile every host's installs:
   ```bash
   scitex-dev ecosystem validate-versions --dry-run       # preview the sync
   scitex-dev ecosystem validate-versions --apply         # execute (all hosts)
   scitex-dev ecosystem fix-mismatches --confirm       # align installed/pyproject/tag
   ```
   For editable installs, a `git pull` in the checkout is enough — but
   the *interpreter that resolves the entry point must be the editable
   one* (the 2026-07-05 "not available yet" episode: the operator's
   shell resolved `scitex-dev` from a **different venv** than the one
   reinstalled; always confirm `which <cli>` → `pip show -f` →
   `Editable project location`).
5. **Rebuild the container base image** (layer 5): so a fresh agent
   boots with the published version baked in, not a stale editable.
6. **Rolling-restart agents** (layer 6): each agent's overlay picks up
   the new base on restart. Restart is **disruptive** (drops the live
   session) — see §6.

## 4. A broken feedback loop *hides* drift (load-bearing lesson)

**2026-07-05 episode.** The self-hosted Spartan CI runner's
`setup-python` was resolving to a dangling tool-cache symlink, so every
`pytest` job crashed at ~15s *before running a single test*. For the
whole outage window, merges to `develop` reported red — but the redness
looked like "the known runner issue," so it was tuned out. Underneath,
the actual test suite (including the `test_audit_all_clean`
self-dogfood test) **never ran**, and PS-2xx audit violations from
several merges accumulated invisibly. The moment the runner was fixed,
they all surfaced at once.

**Rule:** a CI feedback loop that is red *for any reason* is a drift
detector that is turned off. Treat "CI has been red a while (infra)" as
a P1 — not because of the infra, but because **you are now blind to
every new drift the tests would have caught.** Fix or route around the
infra fast; never let green-CI go dark for days.

## 5. The baked-artifact gap and the never-again loop (the north star)

The two layers `validate-versions` can't see (5 = container base image, 6 =
agent overlays), why `deploy-freshness` is no help, the 2026-07-08 baked-SIF
incident, the SoC-split never-again loop (detect / judge / rebuild-remotely /
verify-fail-loud / swap-restart), the parity definition, and keeping the
mechanism general with fleet-specifics in config are in
[21_baked-artifact-drift-loop.md](21_baked-artifact-drift-loop.md).

## 6. Agent rebuild/restart protocol

When infra packages change (`scitex-agent-container`, `scitex-todo`,
`claude-code-telegrammer`), the container/overlay layers (5, 6) are stale until
a rebuild+restart. The protocol — release infra first, rebuild the base image
once, rolling-restart at a coordinated quiet window (never mid-task), interim
env-shim over emergency restart, and batching the wave — is in
[23_agent-rebuild-restart-protocol.md](23_agent-rebuild-restart-protocol.md).

## 7. Documentation drift — the loosely-coupled sibling

The parallel axis — does the doc still match the code it describes? Where it
hides (README, `_skills/`, CLI help vs reference, docstrings, demos,
cross-package refs), the existing scitex-dev detectors, and the three durable
moves (generate from code; put under an audit rule; fix at the point of notice)
are in [22_documentation-drift.md](22_documentation-drift.md).

## 8. Speed doctrine (why this exists)

Every layer that drifts is a debugging session that shouldn't have
happened and a change that isn't actually live. Fast fleet development
requires that **the observe pass (§2) is cheap and habitual, the
reconcile loop (§3) is one command per layer, and the feedback loop
(§4) is never dark.** When those three hold, a change flows from
`develop` to every host, container, and agent in minutes with no
hand-tracking — which is the whole point.
