---
description: |
  [TOPIC] Interface Cli Exceptions
  [DETAILS] SciTeX CLI single-token exceptions — `doctor`, `repl`, `shell`. Banned bare leaves (`version`, bare `completion` command). Canonical `completion` noun group (`completion install [--dry-run]`, `completion status`). Reserved single-token flags.
tags: [scitex-general-interface-cli-exceptions]
---

# §1b. Exceptions (single-token commands)

- Single-token command, **no object needed** — name is already an intransitive verb.
- Transitive verbs (`list`, `start`, `delete`) can **never** be exceptions.

| Exception        | Why                                   |
|------------------|---------------------------------------|
| `doctor`         | Widely recognized health-check idiom  |
| `repl` / `shell` | Invoking it *is* entering the session |

## Banned single-token commands (do **not** add)

- `version` — use the `--version` / `-V` flag instead (see [08_universal-flags.md](08_universal-flags.md)). A bare `version` subcommand is forbidden.
- `completion` as a bare **command** (leaf) — the click auto-generated leaf that dumps a script is banned. A `completion` noun **group** is the canon — see below.

**Rule of thumb:** if any realistic sibling verb exists, it is **not** an exception — add the verb now.

## The `completion` noun group (canonical — operator-confirmed 2026-07-07)

`completion` is a noun with sibling verbs, so it gets a noun group
(§1 tree form):

```
<cli> completion install [--shell {bash,zsh,fish}] [--dry-run]
<cli> completion status
```

- `completion install` — writes the cached completion script + rc
  `source` line (mechanics in §1a
  [03_required-introspection-commands.md](03_required-introspection-commands.md)).
- `completion install --dry-run` — prints the target rc file **and**
  the completion script without touching the filesystem. This subsumes
  and **RETIRES** `print-shell-completion` (piping:
  `eval "$(<cli> completion install --dry-run ...)"`-style usage moves
  to the printed script).
- `completion status` — reports whether completion is wired for this
  binary (cache file present, rc line present, which shell).

The former canon — `install-shell-completion` /
`print-shell-completion` verb-noun compounds — is superseded. Existing
mounts become Phase W warn-forward aliases (§5
[11_deprecation.md](11_deprecation.md)) for `completion install` /
`completion install --dry-run`.

The ban above stays for a bare `completion` COMMAND; a `completion`
GROUP is grammatical (a trailing noun whose subcommands are the verbs).

## Not exceptions (common mistakes)

- `dashboard`, `server`, `repl-mode` — trailing nouns with transitive actions.
  - Browser-based surfaces belong in the canonical `gui` group (§12 [19_gui-commands.md](19_gui-commands.md)); other services use an explicit verb (`server start` or `start-<noun>`).

## Reserved single-token flags (not subcommands — §1 never applied)

- `-h`, `--help`, `--help-recursive`
- `--version`
- `--json`
