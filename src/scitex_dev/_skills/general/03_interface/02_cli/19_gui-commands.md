---
description: |
  [TOPIC] Interface Cli Gui
  [DETAILS] SciTeX CLI canonical `gui` group for every browser-based surface — verbs `open [SURFACE]` (auto-serve), `serve --port --host` (foreground), `status`, `stop`. Django manage.py verbs never mounted.
tags: [scitex-general-interface-cli-gui-commands]
---

# §12. GUI commands — one canonical `gui` group

Operator-confirmed 2026-07-07. Every browser-based surface a package
ships — board, dashboard, Django UI, interactive editor, browser
launcher — mounts under **one group name: `gui`**.

- One instantly-recognizable word, same everywhere.
- Not `django` (too technical), not `browser` (collides with the scitex
  browser-automation domain), not `board` / `dashboard` / `web`
  (per-package drift).

## Fixed verbs

```
<cli> gui open [SURFACE]           # launch in the browser; auto-serves if not running
<cli> gui serve [--port N] [--host H]   # run the server in the FOREGROUND
<cli> gui status                   # is it running? where?
<cli> gui stop                     # stop the running instance
```

| Verb     | Semantics                                                                                          |
|----------|------------------------------------------------------------------------------------------------------|
| `open`   | The user-facing entry point: opens the surface in the browser, **auto-serving first if needed**.    |
| `serve`  | Foreground server (blocks; Ctrl-C to stop). `start`/`stop` stay reserved for **daemonized** lifecycle (§1d catalog) — `serve` is deliberately not `start`. |
| `status` | Report running/not-running, port, pid, URL.                                                         |
| `stop`   | Stop the instance `open` auto-served (or a daemonized one).                                         |

## Multiple surfaces → positional argument

A package with more than one surface passes the surface name as the
argument, not as extra groups:

```
<cli> gui open board
<cli> gui open editor
```

## Migration

Legacy bare leaves — `<cli> gui`, `<cli> board`, `<cli> dashboard`,
`start-dashboard`-style compounds — become Phase W warn-forward aliases
(§5 [11_deprecation.md](11_deprecation.md)) for `gui open [SURFACE]`.

## Django stays internal

Django `manage.py`-ish verbs (`runserver`, `migrate`, `collectstatic`,
`createsuperuser`, …) are **never mounted on a package CLI**. They are
internal implementation; the CLI surface is exactly the four verbs
above. A maintainer who needs `manage.py` runs it directly.

## Help category

`gui` renders under the `Service` category (§4a
[10a_command-categories.md](10a_command-categories.md)).
