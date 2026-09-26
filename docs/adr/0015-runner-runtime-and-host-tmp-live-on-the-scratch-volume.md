# ADR-0015 — Runner runtime and host tmp live on the scratch volume

**Status:** Accepted (2026-09-20); the rule was generalised the same day at operator direction, before anything had relied on the narrower wording
**Owner:** Infrastructure (host storage, fstab); the measurement came from Applications
**Card:** `scitex-dev-801-802-audit-prs-20260919`
**Triggered by:** PR801, whose audit leg failed twice on `[Errno 28] No space left on device`

## Context

On 2026-09-20 the `audit` job on PR801 failed twice with
`ERROR: Could not install packages due to an OSError: [Errno 28] No space left on
device`, while installing the package and audit tooling. The PR itself was
finished: audit green locally, twenty-seven unit tests green, and the three
pytest legs green. The red check was a full disk, and a red check blocks a
merge, so a storage condition presented as a broken change.

The host was compute-02, identified from the API
(`gh api repos/…/actions/jobs/<id> -q .runner_name`) rather than from the path
in the log — the log's directory names the runner *slot*, and the slot number is
not the host number (compute-03's own runner directory is `actions-runner-org`,
with no suffix at all).

Measured storage across the fleet on that date, all four hosts having `/home`
on the root LV:

| host | root LV | host `/tmp` | scratch | runners under `/home` |
|---|---|---|---|---|
| compute-01 | 98G, 76G used, **81%** | root LV | 295G, 39% | 1 |
| compute-02 | 98G, 92G used, **99%** (1.3G free) | root LV | 295G, 12% | 4 |
| compute-03 | 393G, 344G used, **93%** | root LV | 3.0T, 16% | 1 |
| compute-04 | 492G, 290G used, **62%** | root LV | 3.0T, 30% | 3 |

Two hosts have a 98G root LV and a 295G scratch volume; compute-02 is also the
most loaded, hosting four organisation runners. Its runner directories held
30G, and a single runner's 11G decomposes as:

| part | size | regenerable? |
|---|---|---|
| `_work` | 5.7G | yes — checkouts and caches |
| `_tool` | 3.3G | yes — Node/Python toolchains the runner downloads |
| `externals*` | ~1.8G | yes — and two versions are kept at once |
| `_diag` | 526M | yes — diagnostic logs, pure waste |
| `bin*` + `.runner` / `.credentials` | ~240M | **no — this is the installation and the identity** |

So half of the 30G was not `_work` at all. After one runner's `_work` was
relocated to the scratch volume, compute-02 went from 99% to 95% and the audit
job passed in 80 seconds on re-run. The relocation is therefore not
housekeeping: it is what let a finished PR land.

One more property of these hosts matters more than it first appears: on every one
of them `/` and `/scratch` are logical volumes in the SAME volume group on the
SAME physical device (compute-03: `nvme0n1` 3.6T, `ubuntu--vg` holding a 400G `/`
and a 3T `/scratch`). Moving data between them is a **capacity** separation, not
a durability one — a disk failure takes both — and every host still has
unallocated space in that group:

| host | root LV | scratch LV | same device | VG free |
|---|---|---|---|---|
| compute-01 | 100G | 300G | `sda` 489G | 86G |
| compute-02 | 100G | 300G | `nvme0n1` 476.9G | 74G |
| compute-03 | 400G | 3T | `nvme0n1` 3.6T | 251G |
| compute-04 | 500G | 3T | `nvme0n1` 3.6T | 151G |

That column is recorded for completeness and not as a remedy. Extending the root
LV online from that free space was considered and **rejected**, on the operator's
reasoning: enlarging `/` addresses **capacity**, while the condition this ADR
corrects is **placement** — and growth merely defers that problem, because the
same state is met again eventually, only larger. The free space remains available
for genuine growth; the disagreement is about what the fix should be, not about
whether the space exists.

The constraint that makes this hard: `/tmp` is where build tools write, and on
all four hosts it shares the root LV with `/home`. A host can therefore be
unable to run a `pip install` while a 295G–3.0T scratch volume sits at 12–39%
utilisation on the same machine.

## Decision

The rule, stated at the level it applies: **anything regenerable lives on the
scratch volume, whatever it is.** The runner was the case that forced this into
the open, not the scope of the rule — the root LV keeps what cannot be rebuilt,
and every rebuildable thing is asked to live on `/scratch`.

The members measured so far, and the list is expected to keep growing, which is
precisely why the rule is a property ("can it be rebuilt?") rather than an
enumeration:

| member | measured | rebuilt by |
|---|---|---|
| runner `_work` / `_tool` / `externals*` | 15G + 3.3G + 1.8G per host | the next CI job |
| `~/.scitex` overlays and runtime homes | 108G on compute-03 | re-creating the container |
| `/var/lib/containerd` images and snapshots | 67G on compute-03 | re-pulling the image |
| `~/.npm` and language caches | 6.1G on compute-03 | the next install |
| git worktrees | part of 94G on compute-03 | `git worktree` |
| the host's `/tmp` and `/var/tmp` | 2.7G on compute-03 | see item 3 — they are not swept at all |

The table is also why "which host is tight?" is the wrong question. compute-03
has the LARGEST root LV in the fleet and the least headroom, because it holds
more *regenerable* data on the wrong filesystem: 294G of its 342G is `.scitex`
(108G), `proj` (94G) and containerd (67G), and not one byte of that needed to be
there.

1. **The runner installation and its identity stay on the root filesystem** —
   `bin*`, `externals`' executables, `.runner`, `.credentials`. Roughly 240M per
   runner. They are small, and a runner whose identity file vanishes must
   re-register with the organisation rather than simply rebuild.
2. **The runner runtime lives on the scratch volume** — `_work`, `_tool`,
   `externals*`. These are the gigabytes, and every one of them is rebuilt by
   the next job. `_diag` is deleted outright.
3. **The host's `/tmp` and `/var/tmp` move to the scratch volume — the backing
   filesystem moves, the PATH does not.** `/tmp` must keep existing for every
   application that uses it (sockets, lock files, editor and build scratch), so
   nothing may delete it and a bind must never present an empty directory in its
   place. Leaving it on the root LV means every wheel unpacking competes with
   `/home` for the same small filesystem, and leaving it alone is not neutral
   either, because on these hosts **`/tmp` is not tmpfs** — it is a plain
   directory on the root LV, so it does not clear at reboot — and the
   systemd-tmpfiles rule in force is `D /tmp 1777 root root 30d`. Thirty-day
   aging against a workload that writes ~1.4G per CI run means the hourly
   cleanup removes nothing: compute-01 was still holding a directory from four
   days earlier. Age the `ci-*` pattern at about a day, and make the writer put
   its temp on scratch, rather than relying on the sweep.

   A bind over a LIVE `/tmp` also hides the sockets inside it. On compute-03
   that includes the tmux server socket at `/tmp/tmux-1000/default`, and because
   sac's liveness probe is tmux-based, hiding it makes every agent on that host
   read as dead — the input to a restart decision. So this step is a
   maintenance-window change with content preserved first, not an in-place
   toggle, and of everything in this ADR it is the one that must not be done
   casually.
4. **One canonical layout:** `/scratch/ywatanabe/ci/<runner-name>/<runtime-dir>`,
   fleet-wide. A second layout for the same job is how a runner ends up bound to
   an empty directory while another directory holds its content.
5. **Persistence is per-bind, in `/etc/fstab`, with `nofail`, and fstab has
   exactly one writer.** A bind mount does not survive reboot; a lost entry
   reverts silently to the small filesystem, and the condition returns with no
   signal. Two agents editing fstab on one host is the same interleaving hazard
   as two agents mounting one directory. A symlink needs no entry at all — see
   the mechanism below — which is one more reason to reach for it first.

### Mechanism: a symlink first, a bind only when forced

The default mechanism is a **symlink** at the original path, pointing into the
scratch user space (`/scratch/ywatanabe/<thing>`). It keeps the path unchanged
without the properties that made binds dangerous here:

| | symlink | bind mount |
|---|---|---|
| can hide content | no — `ls -l` shows the target | yes, and that is exactly what broke twice |
| survives reboot | yes, by construction | only with a single-writer fstab entry |
| reversible | `rm` the link | `umount`, and only in the right order |

Two exceptions are real, and both push the decision into the tool's own
configuration rather than either mechanism: a tool that resolves the real path
and then composes further paths from it, and a tool that insists on a real
directory. containerd's `root` and Docker's `data-root` are configuration
options, so for `/var/lib/containerd` the setting is the correct lever.

**Durability is not part of what a relocation buys.** `/` and `/scratch` share a
physical device on every host, so anything that must survive a disk failure needs
a backup or a different host, not a different directory. This matters most for
the rule that long-retention data also belongs on the scratch volume: that is a
placement decision, and it confers no redundancy.

### The procedure, because the ordering *is* the decision

6. Relocate in this order: confirm the target is idle → `umount` if already
   bound → move the content within one filesystem → **verify the source
   directory is empty** → `mount --bind`.
7. **Post-condition, mandatory:** after any relocation, assert the content is in
   the expected place **and not in the old one**. "Not in the old one" is
   precisely what an inverted view fakes.

Two independent incidents produced this clause on the same host in one night.
Rsync → verify → bind → *remove the source* places the removal after the step
that inverts the view, so the removal deletes the destination through the mount
and leaves the path bound to an empty directory. A `mv` executed against a
directory whose job may start mid-move half-completes when files disappear under
it. Neither raised an error; both produced a tree that looked relocated. A
checklist would not have caught either — what caught one of them was reading the
filesystem afterwards and finding the same content in two places.

## Consequences

- compute-02 moves from 99% to roughly 80% once `_work`, `_tool` and `externals`
  are relocated, which is the difference between surviving the next
  matplotlib-scale install and failing it again.
- A CI failure caused by storage stops being read as a broken change. The
  failure mode is a resolution/install error on a green code path, which is the
  same class as a merge that never went live: the signal points at the wrong
  thing.
- **New dependency:** builds now require the scratch volume to be mounted. If it
  is not, `/tmp` is an empty directory on the small root LV rather than a
  missing mount, so the failure is a silent capacity regression, not an obvious
  error.
- **Per-host state that is not in git.** Every bind is an fstab entry on one
  machine. Nothing in the repository detects a host that has lost one, and the
  only defence is the reminder in this ADR plus a check at boot. Symlinks remove
  this class entirely, which is the main reason they are the preferred mechanism.
- **Nothing here buys durability.** `/` and `/scratch` sit on the same physical
  device, so a relocation is a capacity and tidiness change. Long-retention data
  moved to the scratch volume is no safer than it was; its protection is a backup
  policy, and this ADR does not provide one.
- `/tmp` does not heal itself here: thirty-day aging against a writer that
  produces ~1.4G per CI run means the hourly sweep is a no-op, so this pressure
  has to be designed out — the writer puts its temp on scratch, and the `ci-*`
  pattern is aged at about a day — rather than waited out.
- The pre-existing exceptions are not evidence against the rule: compute-04
  already carries `actions-runner-org` and the docker runners under
  `/scratch/ywatanabe/ci/`, and compute-01 and compute-04 carry
  `/scratch/ywatanabe/actions-runners/`. Those hosts got it right; this ADR makes
  the rule explicit so the rest are not each re-decided.

## Notes

Surfaced when PR801's audit leg failed twice on `Errno 28`; the operator asked
whether runners belonged on scratch or tmp in the first place, which is the
question this ADR answers. Measurements were taken through the fleet's host
execution rail on 2026-09-20 and are reproducible with `findmnt`, `df -h` and
`du -x --max-depth=1` on each host.

Related: ADR-0006 (one store per host, consumed as a primitive) is the same
instinct applied to state rather than to capacity — one canonical place, used as
a primitive, with no per-consumer inventing.

The rule was generalised on the day of acceptance, on operator direction, once
the fleet breakdown showed the members outgrowing the original wording: the
operator asked why compute-03 — the host with the largest root LV — was the
tightest, and the answer was 294G of regenerable data on the small filesystem
(`.scitex` 108G, `proj` 94G, containerd 67G). The title still names the runner
because the runner was the forcing case, and a title summarises the trigger
rather than the scope.

Immediately available and independent of any relocation: the disposable CI temp
under `/tmp` (`ci-<repo>-<runid>-*`), which was reclaimed fleet-wide on the same
day — compute-01 81%→66%, compute-02 99%→56%, compute-04 63%→53%, roughly 74G
total — by deleting only directories whose run the API reported as completed,
never by directory age alone, and without touching `/tmp` itself or any path
outside that pattern.

Deliberately NOT decided here: whether the runner *installation* should also
live on the scratch volume. It is possible — a fresh registration would repair
it — but it converts a small, stable thing into a thing that must be rebuilt,
and the capacity argument does not require it.
