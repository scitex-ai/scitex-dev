---
description: |
  [TOPIC] Interface Cli Noun Verb Vocabulary
  [DETAILS] Recommended noun & verb vocabulary tables — common nouns by domain group, common transitive verbs by group, intransitive verbs (exception candidates), and the avoid-synonyms table (pick the left). Reuse this vocabulary across packages so a user who learns `list`/`show`/`sync` in one CLI never re-learns `enumerate`/`display`/`reconcile` in the next.
tags: [scitex-general-interface-cli-noun-verb-vocabulary]
---

# §1d. Recommended noun & verb vocabulary

Companion tables to the canonical verb definitions in [06_noun-verb-catalog.md](06_noun-verb-catalog.md).

## Common nouns (hyphenate multi-word)

| Group             | Nouns                                                                                                             |
|-------------------|-------------------------------------------------------------------------------------------------------------------|
| Code / artifact   | `package`, `project`, `module`, `script`, `example`, `template`, `manifest`, `release`, `version`                 |
| Config & docs     | `config`, `profile`, `preset`, `env-var`, `skill`, `docs`, `readme`, `changelog`, `guideline`                     |
| Data / I-O        | `dataset`, `file`, `path`, `cache`, `db`, `index`, `record`, `bibentry`, `figure`, `table`, `paper`, `claim`      |
| Infra / runtime   | `host`, `machine`, `remote`, `tunnel`, `container`, `image`, `server`, `service`, `process`, `job`, `task`, `run` |
| Ecosystem meta    | `ecosystem`, `api`, `mcp`, `tool`, `plugin`, `hook`, `command`, `completion`, `event`, `log`, `dev`, `gui`        |
| Identity / access | `user`, `account`, `token`, `key`, `secret`, `role`, `session`                                                    |

## Common transitive verbs (always need an object)

| Group            | Verbs                                                                                                  |
|------------------|--------------------------------------------------------------------------------------------------------|
| Read             | `list`, `show`, `get`, `find`, `search`, `describe`, `inspect`, `diff`, `tail`                         |
| Create / write   | `create`, `add`, `init`, `generate`, `scaffold`, `clone`, `copy`, `import`, `register`                 |
| Modify           | `update`, `edit`, `rename`, `move`, `merge`, `patch`, `reset`, `restore`, `rollback`                   |
| Delete           | `delete`, `remove`, `purge`, `clean`, `archive`, `revoke`                                              |
| Lifecycle        | `start`, `stop`, `restart`, `pause`, `resume`, `enable`, `disable`, `install`, `uninstall`             |
| Release / deploy | `build`, `compile`, `publish`, `deploy`, `tag`, `ship`                                                 |
| I/O              | `load`, `save`, `read`, `write`, `fetch`, `download`, `upload`, `export`, `convert`, `render`, `parse` |
| Verify           | `validate`, `check`, `test`, `lint`, `format`, `audit`, `verify`, `benchmark`                          |
| Sync / state     | `sync`, `pull`, `push`, `commit`, `stash`, `apply`, `reconcile`                                        |
| Communication    | `send`, `notify`, `broadcast`, `subscribe`, `publish-event`                                            |

## Intransitive verbs (only exception candidates — see [04_exceptions.md](04_exceptions.md))

| Verb            | Use                                      |
|-----------------|------------------------------------------|
| `doctor`        | Self-diagnose installation / environment |
| `repl`, `shell` | Drop into an interactive session         |

- Anything else that looks intransitive is usually a transitive verb with elided object.
- Surface the object: `sync` → `sync-ecosystem`, `validate` → `validate-config`.

## Avoid synonyms (pick the left)

| Prefer     | Avoid                                                                                                                              |
|------------|------------------------------------------------------------------------------------------------------------------------------------|
| `list`     | `ls`, `enumerate`, `index` (verb), `all`                                                                                           |
| `show`     | `display`, `print`, `cat`, `view`                                                                                                  |
| `delete`   | `rm`, `drop`, `destroy`, `kill` (reserve `kill` for signals)                                                                       |
| `create`   | `new`, `make`, `gen` (use `generate` if needed)                                                                                    |
| `update`   | `edit`, `modify`, `set` (use `set` only for single-key config writes)                                                              |
| `sync`     | `reconcile`, `refresh`, `pull-push` (and never bare — always `sync-<object>`)                                                      |
| `push` / `pull` | `sync-to`, `sync-from`, `sync-up`, `sync-down`                                                                                |
| `validate` | `verify`, `check` — `validate` is canonical ecosystem-wide, not a per-package choice                                              |
| `install`  | `setup`, `bootstrap` — scope: `install` = add a feature/binding to an existing system; `init` = create a brand-new project/config |
| `done`     | `resolve`, `complete`, `finish`, `end` (success terminal state)                                                                    |
| `close`    | `cancel`, `wontfix` as verbs — `close --reason <r>` carries the reason                                                             |
| `status`   | `show-status`, `sync-status`, `ss` (nested leaf only — see §1 polysemous rule)                                                     |
