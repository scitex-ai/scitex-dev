# ADR-0015 — Runner runtime and host tmp live on the scratch volume

**Status:** Accepted (2026-09-20)
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

The constraint that makes this hard: `/tmp` is where build tools write, and on
all four hosts it shares the root LV with `/home`. A host can therefore be
unable to run a `pip install` while a 295G–3.0T scratch volume sits at 12–39%
utilisation on the same machine.

## Decision

Split by *what can be regenerated*, and put only the regenerable half on the
scratch volume. `/tmp` follows, because build tools write there.

1. **The runner installation and its identity stay on the root filesystem** —
   `bin*`, `externals`' executables, `.runner`, `.credentials`. Roughly 240M per
   runner. They are small, and a runner whose identity file vanishes must
   re-register with the organisation rather than simply rebuild.
2. **The runner runtime lives on the scratch volume** — `_work`, `_tool`,
   `externals*`. These are the gigabytes, and every one of them is rebuilt by
   the next job. `_diag` is deleted outright.
3. **The host's `/tmp` and `/var/tmp` are bind-mounted from the scratch
   volume.** Leaving `/tmp` on the root LV means every wheel unpacking competes
   with `/home` for the same small filesystem.
4. **One canonical layout:** `/scratch/ywatanabe/ci/<runner-name>/<runtime-dir>`,
   fleet-wide. A second layout for the same job is how a runner ends up bound to
   an empty directory while another directory holds its content.
5. **Persistence is per-bind, in `/etc/fstab`, with `nofail`, and fstab has
   exactly one writer.** A bind mount does not survive reboot; a lost entry
   reverts silently to the small filesystem, and the condition returns with no
   signal. Two agents editing fstab on one host is the same interleaving hazard
   as two agents mounting one directory.

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
  only defence is the reminder in this ADR plus a check at boot.
- `systemd-tmpfiles` must not be allowed to clean the bind targets, so the
  `/tmp` bind cannot rely on `/tmp` being conventionally disposable.
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

Deliberately NOT decided here: whether the runner *installation* should also
live on the scratch volume. It is possible — a fresh registration would repair
it — but it converts a small, stable thing into a thing that must be rebuilt,
and the capacity argument does not require it.
