---
description: |
  [TOPIC] Interface Cli Catalog
  [DETAILS] SciTeX CLI canonical verb definitions (normative) + recommended noun & verb vocabulary — common nouns by domain, transitive verbs by group, intransitive verbs (exception candidates), synonym avoidance, terminal-state verbs (done/close), grammar rules (singular nouns, kebab-case verb-first compounds, no short aliases).
tags: [scitex-general-interface-cli-noun-verb-catalog]
---

# §1d. Canonical verb definitions & noun-verb catalog

Reuse this vocabulary across packages. A user who learns `list` / `show` / `sync` in one CLI should not re-learn `enumerate` / `display` / `reconcile` in the next.

## Canonical verb definitions (normative — operator-confirmed 2026-07-07)

Every package CLI picks from this set first. A verb outside this table
needs a `# why` justification in the package's
`.scitex/dev/cli-audit-dict.yaml`.

| Verb                   | One-line definition                                                                                             |
|------------------------|------------------------------------------------------------------------------------------------------------------|
| `list`                 | Enumerate all objects of a type, one per line/row. Never `ls`, `enumerate`, `all`.                              |
| `get`                  | Fetch ONE object by id/name; data-first, machine-friendly output.                                               |
| `show`                 | Human-oriented display of one object. **Deprecation direction:** `show-<x>` compounds migrate to the polysemous leaf (`show-status` → `<noun> status`) or to `get`; new CLIs prefer `get` for data and `status`/`logs` leaves for reports. |
| `search`               | Full-text / fuzzy query over content; returns ranked matches.                                                   |
| `find`                 | Locate objects by name/glob/filter; returns paths or ids (exact, not ranked).                                   |
| `create`               | Bring a new object into existence. Never `new`, `make`, `gen`.                                                  |
| `delete`               | Permanently remove an object. Never `rm`, `drop`, `destroy`.                                                    |
| `add`                  | Attach an entry to an existing collection (contrast `create`: the collection already exists).                   |
| `remove`               | Detach an entry from a collection without destroying the underlying object (contrast `delete`).                 |
| `update`               | Modify fields of an existing object in place.                                                                   |
| `start` / `stop` / `restart` | Daemonized-service lifecycle ONLY (background process with a pid). Foreground serving is `serve` (see §12 [19_gui-commands.md](19_gui-commands.md)). |
| `install`              | Add a feature/binding to an existing system (completions, hooks, skills).                                       |
| `uninstall`            | Reverse of `install`. Never `setup`/`teardown`.                                                                 |
| `init`                 | Create a brand-new project/config skeleton where nothing existed.                                               |
| `sync`                 | Bidirectional reconcile. **Always object-suffixed** (`sync-skills`, `sync-ecosystem`) — never bare. Directional transfer is NOT `sync`: use `push` / `pull`. |
| `push` / `pull`        | Directional transfer to/from a remote or upstream. Replaces `sync-to` / `sync-from` / `sync-up` / `sync-down`.  |
| `submit`               | Hand a job to a queue/scheduler (SLURM, CI, task runner).                                                       |
| `publish`              | Make an artifact publicly available (PyPI, registry, site).                                                     |
| `deploy`               | Install + activate onto a target environment.                                                                   |
| `validate`             | The canonical checking verb. Prefer over `verify` and `check` everywhere — one checking verb ecosystem-wide.    |

## Terminal-state verbs (normative)

Exactly two verbs close out a work item:

- `done` — terminal state on **success** (`<cli> task done <id>`).
- `close` — terminal state **with a reason** (`<cli> task close <id> --reason wontfix`).

`resolve`, `complete`, `finish`, `end` are banned synonyms — every
package that tracks items uses `done`/`close` and nothing else.

## Grammar rules (normative)

- **Noun groups are SINGULAR**: `task list`, not `tasks list`. One form
  ecosystem-wide; plural groups are audit findings.
- **3+ verbs on a noun → promote to a noun group.** With 1–2 leaf
  actions a compound leaf is fine (see §1
  [02_subcommand-structure-noun-verb.md](02_subcommand-structure-noun-verb.md)).
- **Compounds are kebab-case and verb-first**: `list-python-apis`, not
  `python-apis-list` or `list_python_apis`.
- **No short aliases.** `ss` (for `sync-status`) and friends are
  banned — aliases save four keystrokes and cost every new user a
  lookup. Tab completion (§1a) makes them pointless.

## Recommended noun & verb vocabulary

The common-noun, transitive-verb, intransitive-verb, and avoid-synonyms tables
moved to a sibling leaf to keep this file under the size cap →
[21_noun-verb-vocabulary.md](21_noun-verb-vocabulary.md).
