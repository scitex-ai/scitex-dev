---
description: |
  [TOPIC] Host disk placement
  [DETAILS] Bulky runtime state lives on scratch with a symlink at its home path; root holds only config and small state. Use when placing runner roots, container/image dirs, or overlays, or when diagnosing a full root disk. Measured fleet layout 2026-09-29: compute-02 root 98G, compute-03 root 393G, compute-04 root 492G; /scratch holds terabytes free (compute-02 scratch is a slower SATA SSD — avoid hot-I/O placement there).
tags: [scitex-dev-host-disk-placement]
---

# Host disk placement — bulky state on scratch, symlink at home

**Rule.** Anything bulky and regenerable lives on scratch; its home
path carries a symlink. Root holds config and small state only. A full
root disk with free scratch is always a placement bug, never a capacity
problem.

**Why.** 2026-09-29: compute-02 root hit 100% and killed runner
`scitex-ci-02` mid-job (`No space left on device` writing diag pages)
while scratch sat ~95% free. The hog was three hash-named SIF builds
plus runner roots on the root filesystem — all movable, none load
bearing at its home path.

**What goes where.**

| Tree | Home path | Scratch target |
|---|---|---|
| SAC images (`sac-scitex/`, `sac-base/`) | `~/.scitex/agent-container/containers/<img>/` | `/scratch/ywatanabe/sac-images/<host>/<img>/` (precedent since 2026-09-12) |
| SAC overlays | `~/.scitex/agent-container/containers/overlays/` | `/scratch/ywatanabe/sac-containers/overlays/` |
| Actions runners | `~/actions-runner-<name>/` | `/scratch/ywatanabe/runners/<name>/` (compute-04 precedent: `/scratch/ywatanabe/ci/actions-runner-org`) |
| Runner `_work`/`_tool` bind-mounts | left in place | already scratch-backed by provisioning — never `mv` a mountpoint; symlink the rest around it |

**Procedures that held.**

- Stop the listener first (`kill <Runner.Listener pid>` while idle —
  verify `busy: False` via `gh api orgs/scitex-ai/actions/runners`).
  Moving an open tree across filesystems leaks writes into unlinked
  inodes.
- `mv` fails on bind-mounted subdirs (`Device or resource busy`).
  Symlink every other top-level entry individually and leave mounted
  entries untouched. `mount --move` needs root, which agents do not have.
- Restart via `nohup ./run.sh` from the (possibly symlinked) root and
  confirm `online` via the API before leaving.
- SIF retention is **three** (rollback safety, operator decision
  2026-09-29) — prune older hash-named builds only, never the
  symlink target. On small roots the three live on scratch, which is
  where the policy stops conflicting with capacity.

**Not yet mechanized** (tracked on
`disk-full-is-reported-before-scratch-is-checked-20260919`): SIF
generation pruning, dead-overlay reaping, and an 85%-full alert. Until
those land, placement plus manual pruning is the control.

**Strictness.** At fleet scale symmetry is load-bearing, not cosmetic:
an undocumented exception is re-discovered as a defect every time.
Placement deviations require a written reason next to the rule, and
conformance is checked by audit, not by memory. Operator doctrine
2026-09-29.
