---
description: |
  [TOPIC] The baked-artifact gap and the never-again loop (drift north star)
  [DETAILS] Why `validate-versions` cannot see inside layer 5 (container base
  image) or layer 6 (agent overlays), and why deploy-freshness is no help
  (venv-scoped, zero SIF awareness). The 2026-07-08 incident (baked
  scitex-todo 0.7.32 CPU-spin), the never-again loop split by SoC
  (detect / judge / rebuild-remotely / verify-fail-loud / swap-restart), the
  parity definition ("matches its DECLARED target", not "all hosts identical"),
  and keeping the mechanism general with fleet-specifics in config. Companion to
  13_version-drift-management.md.
tags: [scitex-general-development-version-drift]
---

# The baked-artifact gap and the never-again loop (the north star)

## 5. The baked-artifact gap and the never-again loop (the north star)

`validate-versions` covers layers 1–4, 7, 8 well. It does **not** yet see
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

1. **Detect** — schedule the existing `validate-versions`/drift-report as a
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
