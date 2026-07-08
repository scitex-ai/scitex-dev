---
description: |
  [TOPIC] Version-Drift Management across the distributed SciTeX fleet
  [DETAILS] The single hardest thing about developing the SciTeX ecosystem fast is keeping ONE package's version consistent across every layer it lives in: PyPI, GitHub (develop/main/tags), each host's per-project `.venv`, the agent container base image, each agent's overlay venv, CI, and every editable (`-e`) install. Drift in any layer silently ships stale or broken code and — worse — hides bugs (a broken CI feedback loop lets audit/test violations accumulate invisibly). This skill defines the drift matrix (what version lives where), the reconcile loop (`scitex-dev ecosystem check-versions` and friends), the full release→propagate→rebuild→restart lifecycle, and the agent rebuild/restart protocol. Read this before any multi-package release wave, before asking "why is my change not live yet?", or when reconciling versions across hosts/containers/agents. Companion to 01_version-control.md (manual git flow) and 03_release-automation.md (release commands).
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
| 3 | **Host `ywata-note-win`** | per-project `.venv` editable installs | `ecosystem check-versions -h ywata-note-win` | `check-versions --apply` |
| 4 | **Host `spartan`** | CI-runner + compute venvs | `ecosystem check-versions -h spartan` | `check-versions --apply -h spartan` |
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
scitex-dev ecosystem check-versions                 # Mode 1: observe (all hosts)
scitex-dev ecosystem check-versions --json          # structured, for piping
scitex-dev ecosystem check-versions -p scitex-io    # one package
scitex-dev ecosystem check-versions -h spartan      # one host
```

Supporting probes:

```bash
scitex-dev ecosystem check-sync                     # per-package develop-sha: local vs remote host(s)
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
   scitex-dev ecosystem check-versions --dry-run       # preview the sync
   scitex-dev ecosystem check-versions --apply         # execute (all hosts)
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

`check-versions` covers layers 1–4, 7, 8 well. It does **not** yet see
inside layer 5 (container base image) or layer 6 (agent overlays) — the
two layers that need a rebuild/restart rather than a `pip install`.
`deploy-freshness` (the auto-restart engine for host units) is **no help
here**: it is venv-scoped — it introspects its *own* cron venv via
`importlib.metadata`, not the unit's ExecStart interpreter — and has
**zero awareness of SIF contents**, so it cannot see a stale package
baked into an immutable image. Baked-SIF drift needs a **sibling
detector**, not an extension of deploy-freshness.

**2026-07-08 incident — the gap materializing.** The running sac-base
SIF (built 2026-07-05) had baked `scitex-todo 0.7.32` while PyPI had
moved to 0.7.43. The baked 0.7.32 MCP server CPU-spins (fixed 0.7.39+),
so an immutable image shipped a *known-buggy* dep fleet-wide and
contributed to a host-saturation incident. **Root cause: immutable
artifact + continuous upstream (~1 release/day) + no rebuild trigger +
no scheduled detector.** A SIF bakes whatever the `>=` floors resolve to
*at build time*, then is frozen; nothing updates it, and — critically —
the existing drift report was **never scheduled**, so it only ran when a
human ran it. Nobody was watching.

**The never-again loop.** Ownership is split by concern (SoC):
scitex-dev owns *when + why to rebuild* (policy); `scitex-agent-container`
owns *how* (`sac versions` reporter + `sac image build --remote`
actuator); `scitex-hpc` owns the HPC build recipe.

1. **Detect** — schedule the existing `check-versions`/drift-report as a
   `scitex_dev.jobs` cron so it runs every N minutes, not on demand.
   Side A = `sac versions --json` (the baked/installed truth; a *pure*
   state reporter — no PyPI/policy logic in it). Side B = PyPI-latest.
   Compare against the **declared target** for each consumer.
2. **Judge (policy — scitex-dev)** — triggers, in priority: a baked
   package publishes a release crossing a threshold (**publish-driven is
   the primary trigger** — the release cadence outpaces any age-based
   SLA); a short staleness SLA; a known-buggy-baked denylist (e.g.
   `scitex-todo<0.7.39`); manual. The compare/judgment lives in
   scitex-dev so `sac versions` can stay a pure reporter.
3. **Rebuild REMOTELY** — `sac image build --remote hpc:spartan`. A local
   rebuild OOMs the host (part of the 2026-07-08 incident); Spartan is
   the executor. The build MUST accept **exact target versions**
   (`--target-versions scitex-todo==0.7.46`), never re-resolve `>=`
   floors — otherwise the rebuild re-introduces the same build-time
   nondeterminism that caused the drift.
4. **Verify (fail loud)** — post-build, assert *inside* the SIF that the
   baked version equals the target (`python -c "import scitex_todo as m;
   assert m.__version__=='0.7.46'"`). Never swap an unverified image.
   Emit a machine-readable baked manifest (resolved versions + SIF
   digest + build UTC timestamp + source `.def` commit) so the monitor
   can diff what actually shipped.
5. **Swap + restart** — atomic swap, clean restart (§6).

**Parity = "matches its DECLARED target," not "all hosts identical."**
Consumers legitimately diverge — the Spartan clew-capsule SIF may be
pinned to an older version by design. The monitor flags *deviation from
each consumer's declared target row*, never inter-host difference; a
declared divergence is not drift, and treating it as one is a false
alarm.

**Keep the mechanism GENERAL; put the fleet-specifics in config.** The
drift monitor, the rebuild policy, and the jobs/CRUD surface are *public*
tooling — anyone using SciTeX packages should be able to run them. Our
fleet's particulars (Spartan, specific SIF images, host topology, which
consumer is pinned where) are **not** hardcoded into the mechanism; they
live in a **user-level, git-tracked config** the generic mechanism reads.
That is the general-vs-specific seam: the code ships the *engine*, the
user config declares the *targets*. Which packages to watch is driven by
**ecosystem tags** — the always-present infra packages
(`scitex-agent-container`, `scitex-todo`, `claude-code-telegrammer`) are
tagged `shared`/`infra` in the ecosystem registry, and each project's
monitored set is derived from those tags rather than a hand-kept list.

## 6. Agent rebuild/restart protocol

When **infra packages** change (`scitex-agent-container`,
`scitex-todo`, `claude-code-telegrammer` — the ones every agent's
runtime depends on), the container/overlay layers (5, 6) are stale until
a rebuild+restart. Protocol:

1. **Release the infra packages first** (§3 through step 3) so the image
   build pulls a stable published version, not a moving editable.
2. **Rebuild the base image once** so its baked venv has the new
   versions.
3. **Rolling-restart agents onto the new image** — one at a time, at a
   coordinated low-activity window. A restart drops the agent's live
   session, so:
   - never restart an agent mid-task or mid-operator-session;
   - let each agent reach a natural break and self-restart (or ping
     `scitex-agent-container` for `sac agents restart <name> -y`);
   - a plain restart only picks up the change if the image/deploy was
     rebuilt first — otherwise it re-materializes the same stale state.
4. **Interim workaround** beats a disruptive emergency restart: if a
   change only needs a config/env fix, a targeted `env -u VAR` /
   `unset VAR` shim (cf. the `SCITEX_TODO_AGENT` legacy-var episode)
   keeps the agent working until its natural restart window.

**Answer to "when do I rebuild/restart all agents?"** — batch it:
release the changed infra packages, rebuild the image once, then
rolling-restart at the next quiet window. Don't restart per-merge; the
interim shims cover the gap, and a coordinated wave avoids N disruptive
session-drops.

## 7. Documentation drift — the loosely-coupled sibling

Version drift is about *which code runs where*. **Documentation drift**
is the parallel axis: does the doc still match the code it describes?
It is in some ways harder, because docs are only **loosely coupled** to
code — nothing forces a README, skill, CLI-reference, docstring, or
example to update when the code under it changes, so it drifts silently
and becomes *confidently wrong* (worse than absent — a reader trusts
it). The constitution's Principle 1 is the governing rule:
**documents and skills are never the source of truth; verify against
the code.**

Where it hides (drift layers, doc edition): `README.md` (sections,
badges, install/usage snippets), the `_skills/<pkg>/` tree, CLI
`--help` vs the hand-written CLI-reference, docstrings vs signatures,
`_demo_*.py`/examples vs the current API, and cross-package references
(one package's doc naming another's moved symbol).

Detectors that already exist in scitex-dev — use them, don't reinvent:

```bash
scitex-dev ecosystem audit-all <pkg>        # includes the doc-surface rules below
scitex-dev ecosystem audit-skills <pkg>     # _skills/<pkg>/ §1–§FM structure
```

- README structure / sections / badge rules (PS-1xx) — see
  `_cli/audit/_project/_check_readme_*.py`.
- Skills structure + self-explain quality —
  [04_skills-self-explain.md](04_skills-self-explain.md).
- Doc-surface precedence (which surface wins when two disagree) —
  [05_doc-surfaces.md](05_doc-surfaces.md).

Three durable moves, in preference order (mirror the version-drift
strategy: one SSoT + a cheap detector):

1. **Generate the doc from the code** so it *cannot* drift — CLI
   reference from `--help`, the API tree from introspection
   (`list-python-apis`), config docs from the schema. Generated docs
   are always in sync by construction.
2. **Put the assertion under an audit rule** where prose is
   unavoidable, so a drifted doc becomes a *red check* (the same
   feedback-loop principle as §4) instead of a silent lie.
3. **Fix at the point of notice** — a doc that contradicts the code is
   a bug in the doc; correct it then and there (constitution §3,
   keep-it-tidy), never treat it as "someone else's cleanup."

## 8. Speed doctrine (why this exists)

Every layer that drifts is a debugging session that shouldn't have
happened and a change that isn't actually live. Fast fleet development
requires that **the observe pass (§2) is cheap and habitual, the
reconcile loop (§3) is one command per layer, and the feedback loop
(§4) is never dark.** When those three hold, a change flows from
`develop` to every host, container, and agent in minutes with no
hand-tracking — which is the whole point.
