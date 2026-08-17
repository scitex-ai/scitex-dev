---
description: |
  [TOPIC] Interface Cli Dev
  [DETAILS] SciTeX CLI canonical `dev` group for every self-maintenance surface — the six verbs `daemon`, `cron`, `systemd`, `hooks`, `skills`, `shell` are FIXED. Package plumbing never mounted at top level. Separately, `scitex-dev ecosystem dev` federates declared `JobSpec`s by KIND (cron/timer/service) — a different axis, not a fan-out of these six.
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
directly.

Read the scope of "fixed" precisely, because it has been misread:

- **The six names above ARE fixed.** A self-maintenance surface mounts
  under one of them or it is not §13-conformant. Do not invent a
  seventh.
- **The verbs INSIDE each of the six are NOT fixed.** `{install,
  uninstall, …}` are illustrative; each of the six is a group or a leaf
  as the package needs.

The auditor's docstring compresses this to "§13 enforces the nesting
rather than a fixed verb set", which is true of the INNER verbs and has
been read as meaning the six themselves are optional. They are not.

## Fleet federation — `scitex-dev ecosystem dev`

`scitex-dev` additionally exposes **`scitex-dev ecosystem dev {…}`**.

**It does NOT federate the six verbs above.** It aggregates the
`scitex_dev.jobs` entry points each package publishes (ADR-0008) and
groups them by **`JobSpec.kind`**:

```
scitex-dev ecosystem dev cron      # kind='cron'
scitex-dev ecosystem dev timer     # kind='timer'
scitex-dev ecosystem dev service   # kind='service'
scitex-dev ecosystem dev systemd   # (deprecated) -> service / timer
```

So the two surfaces are indexed on **different axes**, and this is
deliberate:

| | indexed by | source of truth |
|---|---|---|
| `<pkg> dev <verb>` | self-maintenance SURFACE | the package's own CLI |
| `ecosystem dev <kind>` | `JobSpec.kind` | `scitex_dev.jobs` entry points |

Two consequences that have caused real confusion and are written down
here so nobody re-derives them:

- **`cron` means different things in the two.** Under `<pkg> dev` it is
  that package's cron INSTALLER. Under `ecosystem dev` it is the set of
  declared jobs whose `kind` is `cron`. Same word, different referent.
- **`daemon`, `hooks`, `skills` and `shell` have no federated form.**
  There is no `ecosystem dev hooks`. A self-maintenance verb that is not
  a declared `JobSpec` cannot be fanned out, because federation reads
  entry points, not CLIs.

Corrected 2026-08-17. This section previously described `ecosystem dev`
as "the fleet-central federation over every package's own `dev` group —
one place to fan a self-maintenance verb (install hooks, sync skills, …)
across the whole ecosystem". That capability does not exist and never
did: `ecosystem dev` has no `hooks` or `skills` leaf to fan. The claim
also made the two verb sets look like a contradiction — doctrine
requiring `systemd` while the implementation deprecated it — when they
are simply different axes, and only the FEDERATED `systemd` is
deprecated (in favour of the finer `timer` / `service` kinds). The
per-package `<pkg> dev systemd` in *Fixed verbs* above is unaffected.

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
