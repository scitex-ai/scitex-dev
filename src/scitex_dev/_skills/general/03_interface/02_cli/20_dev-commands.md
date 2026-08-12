---
description: |
  [TOPIC] Interface Cli Dev
  [DETAILS] SciTeX CLI canonical `dev` group for every self-maintenance surface — verbs `daemon`, `cron`, `systemd`, `hooks`, `skills`, `shell`. Package plumbing never mounted at top level; scitex-dev federates the fleet via `scitex-dev ecosystem dev`. §13a: sibling commands keep ONE level of abstraction — an intent name never sits beside a mechanism name.
tags: [scitex-general-interface-cli-dev-commands]
---

# §13. Dev commands — one canonical `dev` group

Operator directive. Every self-maintenance surface a package ships —
its daemon supervisor, cron installer, systemd units, git hooks, skills
sync, dev shell — mounts under **one group name: `dev`**.

- A package's top-level CLI is its DOMAIN. Self-maintenance plumbing is
  housekeeping, and housekeeping belongs under `dev`.
- `<pkg> --help` then reads as the tool, not the tool's own upkeep.

## Fixed verbs

```
<cli> dev daemon   {start,stop,status,...}   # long-running supervisor
<cli> dev cron     {install,uninstall,...}   # scheduled jobs
<cli> dev systemd  {install,uninstall,...}   # unit files
<cli> dev hooks    {install,uninstall,...}   # git / pre-commit hooks
<cli> dev skills   {sync,list,...}           # bundled skill files
<cli> dev shell                              # dev / repl shell
```

`dev` is a **group only** — it never takes a positional argument
directly. Each of the six verbs is itself the sub-surface (a group or a
leaf as the package needs); §13 enforces the **nesting**, not any fixed
verb set inside each one.

## Fleet federation — `scitex-dev ecosystem dev`

`scitex-dev` additionally exposes **`scitex-dev ecosystem dev {…}`** as
the fleet-central federation over every package's own `dev` group — one
place to fan a self-maintenance verb (install hooks, sync skills, …)
across the whole ecosystem instead of visiting each package CLI.

## Migration

Legacy top-level forms — `<cli> cron`, `<cli> daemon`, `<cli> hooks`,
… — become Phase W warn-forward aliases (§5
[11_deprecation.md](11_deprecation.md)) that **fail-loud-redirect** to
`<pkg> dev <verb>`. Either move the command under a `dev` group
directly, or register a `scitex_dev.ecosystem.deprecated_alias()`
forwarding to `dev <verb>`.

## Help category

`dev` renders under the `Service` category (§4a
[10a_command-categories.md](10a_command-categories.md)).

# §13a. One level of abstraction per group

Constitution, *§3 Craft*:

> Name the INTENT, not the MECHANISM — and keep one level of abstraction
> per axis. If two values differ only in how they are implemented, the
> mechanism belongs in its own field, not welded into the type.

Sibling commands under one parent are a **menu**. Click renders them as
the alternatives available at that level, so a menu that offers an
*intent* ("run this continuously") beside a *mechanism* ("via crontab")
is asking the reader to choose between **what they want** and **how it
is done** — and those are not alternatives to each other.

## The diagnostic

Ask it of any two siblings:

> **If two names differ only in HOW the thing is done, they are ONE
> intent plus a `--mechanism`-shaped axis — not two groups.**

| Pair                | Verdict                                                                                  |
|---------------------|------------------------------------------------------------------------------------------|
| `daemon` / `cron`   | **Mixed.** `daemon` says *run continuously* (intent); `cron` says *crontab* (a scheduler). |
| `service` / `timer` | **Mixed.** `service` is the mechanism-agnostic intent; `timer` is one systemd unit type.   |
| `cron` / `systemd`  | Same level (both schedulers) — but a **mechanism** level, so neither may sit beside an intent. |
| `hooks` / `skills`  | Same level. Both name an **artefact** the package owns; a different axis entirely.         |

This is the same defect the job-kind taxonomy already fixed one layer
down, in `scitex_dev/jobs/_kinds.py`: the stored kinds `service` /
`timer` / `cron` mixed one intent with two mechanisms, so the
intent-level vocabulary became `daemon` / `periodic` with the scheduler
resolved as a **separate axis**.

## The shape that is right

```
<cli> dev daemon   {start,stop,status}                intent — run continuously
<cli> dev periodic {list,install,uninstall}           intent — run on a schedule
      --mechanism {systemd,cron,respawn,auto}         how    — its own axis
```

## When a mechanism word IS a legitimate group

A mechanism word may name a group when it names the **artefact the
package owns**, not the way a job runs. `<cli> dev cron` meaning *manage
my crontab entries* is a noun — the same kind of noun as `hooks` (git
hooks) or `skills` (skill files) — and it is fine.

**The test is the SIBLING, not the word.** `dev cron` alone is fine;
`dev {daemon, cron}` is not, because there `cron` is being offered as an
alternative to an intent.

## Enforcement

Rule **§13a**, `_cli/audit/_summary/_abstraction_level.py`. It walks
every group in the command tree and flags a parent whose **visible**
direct children contain both an intent name and a mechanism name from
the same axis. One finding per offending parent — the defect is the
menu, not any single command on it.

It is **reporting-only** and deliberately **not** a general
"detect abstraction levels" classifier: no rule can tell an intent from
a mechanism by inspecting an English word, and a rule that guesses
false-positives on somebody's legitimate domain noun, gets excluded, and
then gets deleted. The rule ships one hand-written axis family
(scheduling / supervision), seeded from vocabulary the fleet has already
ruled on in `jobs/_kinds.py` and `_dev_group.py`. Widen it when a second
real case appears, never speculatively.

Hidden commands do not count: a Phase W warn-forward alias is hidden by
construction, so a package that has already migrated is not re-flagged.

## Migrating out of a mixed menu

A CLI verb is a **published contract**, so collapsing `cron` / `systemd`
into `periodic --mechanism` is a **MIGRATION, not a rename**: register a
Phase W `scitex_dev.ecosystem.deprecated_alias()` for the old spelling
first (§5 [11_deprecation.md](11_deprecation.md)) and remove it later.
The old names live in crontabs, unit files, shell scripts and agent
prompts that cannot be grepped from any one repository.

## Known standing finding

`scitex-dev ecosystem dev` mounts one group per JobSpec kind —
`service`, `timer`, `cron` — plus the deprecated `systemd` alias group,
all as visible siblings. That is a mixed menu by this rule's own
definition, and it is scitex-dev's own CLI. It is recorded here rather
than exempted: the remedy is the migration above, not a carve-out.
