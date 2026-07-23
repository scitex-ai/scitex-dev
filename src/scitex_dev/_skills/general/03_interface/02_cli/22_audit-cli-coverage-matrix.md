---
description: |
  [TOPIC] Interface Cli Audit Coverage Matrix
  [DETAILS] Auditor coverage of each CLI standardization rule (§1–§11) by `scitex-dev ecosystem audit-cli` — which rules are enforced statically (`yes`), which are best-effort heuristics (`partial`), and which are not yet auditable (`no`/`TODO`), with per-rule notes on the static vs behavioral checks.
tags: [scitex-general-interface-cli-audit-cli-coverage-matrix]
---

# §1e. `audit-cli` coverage matrix

Companion to [07_audit-cli.md](07_audit-cli.md).

## Coverage matrix

Auditor coverage of each rule (`yes` = enforced statically; `partial` = best-effort heuristic; `no` = not yet auditable):

| Rule | Topic                                        | Coverage  | Notes                                                                |
|------|----------------------------------------------|-----------|----------------------------------------------------------------------|
| §1   | Noun-verb subcommand structure               | yes       | Click tree walk, token classification.                               |
| §1a  | Required introspection commands              | yes       | Presence + `--json` static; `-v|-vv|-vvv` monotonic ladder behavioral (`--behavioral`). |
| §1b  | Banned bare leaves (`version`, `completion`) | yes       | Hard-coded denylist at any depth.                                    |
| §1c  | Pass-through entry points                    | no        | Auditor cannot statically detect verbatim-forward entries.           |
| §1d  | Vocabulary in catalog/dict/Moby              | yes       | Layered lookup; warns on `unknown`.                                  |
| §1e  | (this section — the auditor itself)          | n/a       |                                                                      |
| §1f  | Non-canonical verb synonyms                  | yes (warn) | Doctrine-06 synonym map over leaf names / verb tokens; `verb_exceptions:` (with `# why`) exempts. |
| §2   | Universal flag presence                      | yes       | Root: `--version`/`-V`, `--help-recursive`, `--json` (parseable). Leaves: `--json` on read verbs; `--dry-run` and `--yes`/`-y` on mutating verbs. |
| §3   | Exit code conformance                        | partial   | Top-level bogus-flag returns 2 (behavioral; `--behavioral`).         |
| §4   | Help format                                  | partial   | Heuristic: looks for "example", "$ ", or "e.g." in help/epilog. Skipped for spec-built commands (§4b subsumes). |
| §4b  | Spec-built help (`CliHelp`)                  | yes (warn) | `_help_spec` presence on every non-hidden, non-pass-through command. |
| §5   | Deprecation ladder (W → E → R)               | partial   | Static: `cmd._deprecated_alias` metadata (target resolves, `remove_in` set). Behavioral (`--behavioral`): phase-W exits 0 + prints `deprecated`; phase-E exits 2; metadata-less hidden leaves keep the legacy non-zero + redirect-hint contract. |
| §5b  | Umbrella subcommand passthrough              | TODO      | Diff `scitex <short> --help` vs standalone `--help` (modulo prog-name); flag hand-typed wrappers + `subprocess.call(["scitex-<pkg>", ...])` shapes; flag hardcoded brand strings (`scitex-<pkg>`, `socialia`, …) in help bodies that will be rendered under the umbrella. See [05a_umbrella-passthrough.md](05a_umbrella-passthrough.md). |
| §6a  | Env var prefix `SCITEX_<PKG>_*`              | partial   | Static source scan flags bare-pkg prefix; cross-pkg `SCITEX_*` allowed. |
| §6b  | Config path fallback documented in `--help`  | yes       | Greps root help/epilog for `config.yaml`, `$SCITEX_<PKG>_CONFIG`, or `~/.scitex/`. |
| §7   | CLI ↔ MCP parity                             | no        | Could compare `list-python-apis` and `mcp list-tools` output (TODO). |
| §8   | stdout/stderr discipline                     | partial   | `list-python-apis --json` parsed as JSON (behavioral; `--behavioral`). |
| §10  | CLI startup speed (`import <pkg>` < 500ms)   | yes       | Cold-start measurement in fresh subprocess. Threshold: 500ms (Click runs program once per Tab press). Remediation: PEP 562 lazy `__getattr__` in `__init__.py`. |
| §11  | CLI framework conformance (Click canonical)  | yes       | Static scan of entry-point module + sibling `_cli/` dir for `import argparse` / `from argparse`. Click is canonical for every scitex-* CLI; argparse causes drift (doubled subparser metavar, manual `--json` wiring per parser, no shared CategorizedGroup). |
