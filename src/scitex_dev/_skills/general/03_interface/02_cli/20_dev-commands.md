---
description: |
  [TOPIC] Interface Cli Dev
  [DETAILS] SciTeX CLI canonical `dev` group for every self-maintenance surface — verbs `daemon`, `cron`, `systemd`, `hooks`, `skills`, `shell`. Package plumbing never mounted at top level; scitex-dev federates the fleet via `scitex-dev ecosystem dev`.
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
