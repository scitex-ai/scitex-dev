---
description: |
  [TOPIC] Interface Cli Audit
  [DETAILS] SciTeX CLI automated audit — `scitex-dev ecosystem audit-cli`. Token classification, what it flags, custom dict format.
tags: [scitex-general-interface-cli-audit-cli]
---

# §1e. Automated check — `scitex-dev ecosystem audit-cli`

- Opt-in linter that walks a package's Click command tree.
- Warns (never errors) on §1 / §1d violations.
- Behind the `cli-audit` extra so ordinary consumers don't pull dictionary data.

```bash
pip install 'scitex-dev[cli-audit]'
scitex-dev ecosystem audit-cli <package-name>
scitex-dev ecosystem audit-cli <package-name> --behavioral   # also run subprocess checks (slow)
scitex-dev ecosystem audit-cli <package-name> --baseline     # ratchet: record once, fail only on NEW
```

## Baseline ratchet (`--baseline`)

Adopt the auditor incrementally: the first `--baseline` run records every
current violation fingerprint (rule id + command path + message-invariant
part, digits normalized) to `.scitex/dev/cli-audit-baseline.yaml` and
exits 0. Later runs — with the flag OR whenever that file exists —
suppress the recorded violations (a count is shown) and fail/warn only on
NEW ones. To re-record, delete the file and re-run with `--baseline`.
Pass `--baseline PATH` to use a non-default file.

## Token classification (first hit wins)

1. `<project-root>/.scitex/dev/cli-audit-dict.yaml` — project-local dict.
2. `~/.scitex/dev/cli-audit-dict.yaml` — user dict.
3. Bundled catalog from [06_noun-verb-catalog.md](06_noun-verb-catalog.md).
4. Moby POS dictionary (~130k English words, vendored ~900 KB gzipped).
5. Otherwise → warning to extend the custom dict.

## What it flags (warn-only)

- §1 leaf token is a noun without a verb (`<cli> dashboard` → suggests `start-dashboard`).
- §1 bare transitive verb at top level (`<cli> list` → demands `list-<object>`). **Exception:** if the verb declares a required positional argument (`<cli> install <pkg>`), the object is right there; the warning is suppressed.
- §1 group (non-leaf) token is a verb (groups must be nouns).
- §1a missing introspection commands (`list-python-apis`, `mcp list-tools`, `install-shell-completion`, `print-shell-completion`) and their `--json` flag. Tab completion is a §1a baseline requirement — without it, users typing `<cli> <TAB>` get nothing (the 2026-05-06 scitex-hpc symptom). *Note:* the doctrine canon has moved to `dev list-python-apis` (§11 [18_dev-subgroup-and-ecosystem-placement.md](18_dev-subgroup-and-ecosystem-placement.md)) and the `completion install`/`completion status` group (§1b [04_exceptions.md](04_exceptions.md)); the auditor still checks the legacy names until slice 4 of the CLI-standardization plan updates it.
- §1b banned bare leaves (`version`, `completion`).
- §1d tokens not in catalog/dict/Moby.
- §1f non-canonical verb synonym (WARN) — data-driven map seeded from the [06_noun-verb-catalog.md](06_noun-verb-catalog.md) synonym tables (`ls`→`list`, `resolve`/`complete`→`done`, `setup`→`install|init`, `sync-to`/`sync-from`→`push-<object>`/`pull-<object>`, `show-status`→`status`, …). Matched against the full leaf name first, then the verb token. Escape hatch: a `verb_exceptions:` list in `.scitex/dev/cli-audit-dict.yaml`; every entry needs an inline `# why` comment (undocumented entries still exempt, but the missing comment is itself warned about).
- §4b help not built from a `CliHelp` spec (WARN) — spec-built help ([10_help-format.md](10_help-format.md)) is the enforced construction method; commands lacking `_help_spec` (set by `SpecCommand`/`SpecGroup`) warn. Spec-built commands skip the §4 example sniff — `CliHelp` validation already guarantees leaves declare ≥1 example.
- §5 deprecated-alias metadata — every `cmd._deprecated_alias` (set by `click_compat.deprecated_alias()`) is verified statically: `target` must resolve in the command tree and `remove_in` must be set. With `--behavioral`, hidden leaves are probed phase-aware: phase-W aliases must exit 0 AND print `deprecated` on stderr; phase-E must exit 2; metadata-less hidden leaves keep the legacy non-zero + redirect-hint expectation.
- §2 missing universal flags at top: `--version`/`-V`, `--help-recursive`, **`--json`** (so `<cli> --json` parses without crashing); on read verbs: `--json`; on mutating verbs: `--dry-run` and `--yes`/`-y`.
- §4 missing concrete example in command help/epilog (Click guarantees the Usage line).
- §10 CLI startup speed — `import <top-level-module>` cold-start exceeds 500ms.
- §11 CLI framework conformance — entry-point module or sibling `_cli/` imports `argparse`. Migrate to Click (canonical). argparse adds drift (doubled subparser metavar in --help, no shared CategorizedGroup, manual `--json` wiring per parser, no `--help-recursive` plumbing, **no `click.shell_completion` so tab completion does not exist**). Click runs the program once per Tab press; slow import = unusable tab-completion. Remediation: PEP 562 lazy `__getattr__` in `__init__.py` (see python-api skill 04 "PEP 562 module __getattr__" section). Known holdouts as of 2026-05-06: scitex-scholar (argparse-based; ships all 4 mcp subcommands but cannot expose tab completion until migrated to click).
- §5b umbrella drift — for any package present in both the umbrella (`scitex/cli/<short>.py`) and the standalone (`scitex_<pkg>._cli` / branded `<brand>._cli`):
  - Flag the umbrella file if it defines a `click.command` that calls `subprocess.run`/`subprocess.call` with the standalone CLI as argv[0]. The canonical shape re-exports the standalone's `click.Group` and only sets `.name`.
  - Flag the umbrella file if it hand-types a help body that duplicates standalone subcommand names (heuristic: any standalone leaf token literal appearing inside the umbrella file). The umbrella owns only the namespace name.
  - Flag standalone help/epilog/docstring bodies that contain a hardcoded brand literal (`scitex-<pkg>` or the entry from `ECOSYSTEM["<pkg>"].pypi_name` for branded packages). Suggest `{prog}` (formatted from `ctx.find_root().info_name`) or `<cli>` placeholder.

## Coverage matrix

The per-rule auditor coverage matrix moved to a sibling leaf to keep this file
under the size cap → [22_audit-cli-coverage-matrix.md](22_audit-cli-coverage-matrix.md).

## Periodic auditing during development

For how to run `audit-all` continuously while editing a package — cron / tmux / agent recipes, the JSON contract for programmatic consumers, and Claude Code-specific autonomous mechanisms — see [`05_development/02_periodic-audits.md`](../../05_development/02_periodic-audits.md).

This file (`07_audit-cli.md`) is about *what* `audit-cli` checks; the periodic-audits skill is about *when* and *how* to invoke it during development.

## Custom dict format

```yaml
# cli-audit-dict.yaml
nouns:
  - bibentry
  - openurl
transitive_verbs:
  - enrich
  - deduplicate
intransitive_verbs:
  - vacuum
verb_exceptions:               # §1f opt-outs — every entry needs a `# why`
  - resolve  # why: matches upstream GitHub issue terminology
```

## Operational notes

- Run in CI for every `scitex-*` repo.
- Never fails the build, but drift becomes visible.
- Custom dicts are **additive**: they extend the catalog with package-specific tokens, never reclassify or override existing ones. A token already classified by the canonical catalog keeps its class even if also listed in a dict.
