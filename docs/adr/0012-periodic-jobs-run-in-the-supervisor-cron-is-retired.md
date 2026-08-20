# ADR-0012 — SciTeX periodic jobs run in the supervisor; cron is retired

**Status:** Accepted
**Owner:** scitex-dev, as the fleet's job-federation and deploy surface
**Ruling:** operator, 2026-08-20
**Implementation:** `scitex_dev._supervisor._periodic.PeriodicRunner` (runs them) + `scitex_dev._cli.ecosystem._cmds._up_cron_retire` (removes the old surface)
**Supersedes:** the timer→cron lowering introduced under the 2026-06-14 supervisor policy
**Related:** ADR-0008 (job declarations stay entry-point only)

## The ruling

> 「サイテクス系の定期ジョブは全てスーパーバイザー経由でサイテクスデブで一本化」
>
> Every SciTeX periodic job is unified through the supervisor, via scitex-dev.

Rendered in English above; the original was Japanese, which by standing rule
does not appear on public surfaces.

## Why this exists

The 2026-06-14 policy said systemd shows EXACTLY one unit for the fleet —
`scitex-dev-ecosystem.service` — with `kind="service"` JobSpecs becoming
supervisor children and `kind="timer"` JobSpecs lowering to lines in a managed
crontab block. The first half is unchanged. The second half is now wrong, and
it was wrong for a while before anyone noticed, because BOTH halves worked.

`SupervisorRuntime.discover_periodic_jobs()` returns every non-service JobSpec
and feeds `PeriodicRunner.tick()` on the same clock as the child reconcile. It
has been doing so in production. Measured 2026-08-19, `~/.scitex/dev/runtime/
periodic-executions.jsonl`:

| host | execution records |
|---|---|
| scitex-compute-04 | 32,638 |
| scitex-compute-02 | 29,530 |
| ywata-note-win | 40,578 |

So `ecosystem up`'s cron lowering was installing a **second scheduler for jobs
already running**. That is not a theoretical hazard. On 2026-08-19 a peer agent
read the command correctly, ran `ecosystem up --yes` across four hosts, and
installed 29–35 crontab entries per host — every one a duplicate. The operator
stopped it:

> 「クロンは使わないと言う話でしたよね」 — we agreed not to use cron.

The peer's action was reasonable and their reading of the command was right.
The code path is what made a correct action wrong. A command that offers a
retired deployment surface will be used to deploy on it.

## The decision

1. **Periodic jobs run in the supervisor.** timer-kind AND cron-kind. One
   clock, one process, one execution log.
2. **`ecosystem up` no longer installs a crontab block.** The lowering, the
   per-job refusal, and the `timeout_sec`-carrying prefix leave the up flow
   with it.
3. **`ecosystem up` REMOVES the managed block.** The block's correct content
   is empty, so a reconcile converges it to empty and reports how many lines
   it took out. Only the `BEGIN`/`END` managed region is touched; the rest of
   the user's crontab is not scitex-dev's.
4. **`--allow-lossy-timer-lowering` is removed, not deprecated.** Nothing
   lowers, so the flag controls nothing. An accepted flag that does nothing is
   worse than a rejected one: the caller believes they asked for something.

## What this costs, stated plainly

Two improvements landed hours before this decision and are now removed from the
up flow:

- **#709** made an unlowerable JobSpec refuse per-job instead of aborting the
  whole block (measured: one bad spec had left three hosts with zero cron
  entries and froze a fourth on nine stale lines).
- **#710** carried `timeout_sec` onto the cron line as a `timeout <N> ` prefix
  so the declared bound survived lowering.

Both were correct and both improved a surface this ADR retires. They were not
wasted — #709's refusal is what drove a peer to make ten JobSpecs self-bounding,
and that fix outlives the path that forced it. But the honest record is that
the surface was being polished after the policy that retires it already existed.

## Consequences

- A host that had a managed block becomes single-managed on the next
  `ecosystem up --yes`, and says how many lines it removed.
- A host that never had one reports "no managed block present (correct)" rather
  than passing silently, so an absent block is distinguishable from a failed
  read.
- The `_up_timer_lowering` / `_up_timer_losses` modules stay on disk: the
  standalone `ecosystem cron` CLI still exposes them, and retiring THAT surface
  is a separate decision with its own consumers.
- A leaf that wants a periodic job declares a JobSpec and nothing else. There is
  no second place to put one, which is the point.
