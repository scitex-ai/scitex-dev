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

## Web framework — Django only

Operator-confirmed 2026-07-12: every package GUI is built on **Django**,
not Flask or another micro-framework. This is not a style preference —
**scitex-hub mounts each tool's GUI as a plugin (a guarded `THIRD_PARTY_APPS`
append + URL include into hub's own Django project, per scitex-storage's
reference plugin, scitex-hub#359)**, and a Flask app structurally cannot be
mounted that way. A tool whose GUI is Flask can serve standalone but can
**never** become a scitex-hub plugin — that gap is the reason this rule
exists, not a hypothetical. Any package still on Flask (or another
non-Django stack) for its GUI needs to migrate before it can join the
hub-plugin architecture (§ARCHITECTURE below in the coordination card;
see `scitex-hub-gui-plugin-host-architecture-*` for the plugin-host side).

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
| `serve`  | Foreground server (blocks; Ctrl-C to stop). **Headless only** — never opens a browser, never takes a `--no-browser` flag (browser-launching is exclusively `open`'s job). `start`/`stop` stay reserved for **daemonized** lifecycle (§1d catalog) — `serve` is deliberately not `start`. Must expose a **browsable HTTP root**, not a WS-only endpoint — a GUI whose `serve` only speaks WebSocket is not browser-usable and fails this rule. |
| `status` | Report running/not-running, port, pid, URL.                                                         |
| `stop`   | Stop the instance `open` auto-served (or a daemonized one).                                         |

`gui` itself is a **group only** — it never takes a positional argument
directly (confirmed live 2026-07-12: a `gui [SOURCE]` leaf shape breaks
`gui serve`, since "serve" gets parsed as the positional value instead
of resolving to the `serve` subcommand). Any per-invocation argument
(a source file, a project path, …) belongs on `open`, not on the group.

## Multiple surfaces → positional argument

A package with more than one surface passes the surface name as the
argument, not as extra groups:

```
<cli> gui open board
<cli> gui open editor
```

## Ports — the 3129X block

Standalone GUI servers share one fixed, contiguous port block —
**3129X**, continuing the existing SciTeX web-port scheme (crossref
31291, openalex 31292, audio 31293, scitex-hub staging/dev
31294/31295). Each tool gets **one fixed port**, no incrementing on
repeated starts — `gui serve` binds the tool's fixed port; the runtime
state file makes this idempotent, so a re-run reuses the running
instance instead of stacking a second one on the next free port.

| Tool             | Port  |
|------------------|-------|
| figrecipe        | 31296 |
| scitex-scholar   | 31297 |
| scitex-writer    | 31298 |
| scitex-todo      | 31299 |
| (future GUIs)    | 31290, next free |

This block is orthogonal to the `3129X` reverse-tunnel ports used by
scitex-hub for staging/dev — those stay as-is; this table is the
**local standalone-GUI** block specifically.

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
