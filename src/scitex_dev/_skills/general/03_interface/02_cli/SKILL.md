---
description: |
  [TOPIC] Interface Cli
  [DETAILS] Canonical CLI design convention for every SciTeX package — predictable CLI surface, no interactive commands, subcommand structure (noun → noun → … → verb), canonical verb definitions, recommended commands (dev list-python-apis, mcp, skills, docs, completion install/status), flags (--version|-V, --verbose|-v, --help|-h, --help-recursive, --json, --dry-run, --quiet|-q, --yes|-y), exit codes, help format + fixed command categories + CliHelp spec, three-phase deprecation ladder, env var namespace, config precedence, MCP parity, stdout/stderr discipline, dev subgroup + ecosystem placement, canonical gui group.
tags: [scitex-general-interface-cli-index]
---

# SciTeX CLI Convention (Canonical) — Index

Canonical CLI rules for every `scitex-*` package. Split into focused files; load only the section you need.

## Open TODOs

- [TODO.md](TODO.md) — open items, package sweeps, design questions.

## Sections

| File                                                                                              | Topic                                                              |
|---------------------------------------------------------------------------------------------------|--------------------------------------------------------------------|
| [01_overview.md](01_overview.md)                                                                  | Scope; what's covered, what isn't                                  |
| [02_subcommand-structure-noun-verb.md](02_subcommand-structure-noun-verb.md)                      | §1 — noun-verb chain, tree vs compound leaf, ambiguous tokens      |
| [03_required-introspection-commands.md](03_required-introspection-commands.md)                  | §1a — `list-python-apis` and `mcp list-tools` with `-v|-vv|-vvv`   |
| [04_exceptions.md](04_exceptions.md)                                                              | §1b — single-token commands (`doctor`, `repl`/`shell`); banned bare leaves |
| [05_pass-through.md](05_pass-through.md)                                                          | §1c — verbatim-forwarding entry points exempt from §1              |
| [05a_umbrella-passthrough.md](05a_umbrella-passthrough.md)                                        | §5b — umbrella `scitex` re-exports standalone click groups; brand rewrite (e.g. socialia → `scitex social`) |
| [06_noun-verb-catalog.md](06_noun-verb-catalog.md)                                                | §1d — canonical verb definitions, noun & verb vocabulary, terminal verbs (`done`/`close`), grammar rules, synonym avoidance |
| [07_audit-cli.md](07_audit-cli.md)                                                                | §1e — `scitex-dev ecosystem audit-cli` linter                      |
| [08_universal-flags.md](08_universal-flags.md)                                                    | §2 — required flags, no interactive prompts                        |
| [09_exit-codes.md](09_exit-codes.md)                                                              | §3 — exit code semantics                                           |
| [10_help-format.md](10_help-format.md)                                                            | §4 — required `--help` output structure; `CliHelp` spec-built help |
| [10a_command-categories.md](10a_command-categories.md)                                            | §4a — fixed ordered help categories (Core … Other), `CategorizedGroup` |
| [11_deprecation.md](11_deprecation.md)                                                            | §5 — three-phase ladder Warn → Error → Removed, parameter-level warning |
| [12_config-and-env.md](12_config-and-env.md)                                                      | §6 — env var namespace, config file precedence                     |
| [13_mcp-parity.md](13_mcp-parity.md)                                                              | §7 — CLI ↔ MCP tool parity                                         |
| [14_stdout-stderr.md](14_stdout-stderr.md)                                                        | §8 — stream discipline                                             |
| [15_audit-checklist.md](15_audit-checklist.md)                                                    | §9 — manual audit checklist                                        |
| [16_example.md](16_example.md)                                                                    | Reference CLI shape (`scitex-plt`)                                 |
| [17_option-positional-ordering.md](17_option-positional-ordering.md)                              | §10 — options on either side of positional must both parse (PS-134) |
| [18_dev-subgroup-and-ecosystem-placement.md](18_dev-subgroup-and-ecosystem-placement.md)          | §11 — per-package `dev` subgroup; ecosystem ops only under `scitex dev ecosystem` |
| [19_gui-commands.md](19_gui-commands.md)                                                          | §12 — canonical `gui` group (`open`/`serve`/`status`/`stop`)       |
| [21_noun-verb-vocabulary.md](21_noun-verb-vocabulary.md)                                          | §1d — recommended noun & verb vocabulary tables (nouns, transitive/intransitive verbs, synonym avoidance) |
| [22_audit-cli-coverage-matrix.md](22_audit-cli-coverage-matrix.md)                                | §1e — per-rule `audit-cli` coverage matrix                        |

## Cross-references

- **Specialization skills** back-link to this directory at `<repo>/src/<pkg>/_skills/<pkg>/convention-cli.md` (or equivalent).
- Each specialization lists the package's concrete noun catalog and exceptions.
