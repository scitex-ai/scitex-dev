---
name: interface-cli-audit
description: SciTeX CLI automated audit — `scitex-dev ecosystem audit-cli`. Token classification, what it flags, custom dict format.
user-invocable: false
tags: [scitex-python, scitex-general, cli]
---

# §1e. Automated check — `scitex-dev ecosystem audit-cli`

- Opt-in linter that walks a package's Click command tree.
- Warns (never errors) on §1 / §1d violations.
- Behind the `cli-audit` extra so ordinary consumers don't pull dictionary data.

```bash
pip install 'scitex-dev[cli-audit]'
scitex-dev ecosystem audit-cli <package-name>
scitex-dev ecosystem audit-cli <package-name> --behavioral   # also run subprocess checks (slow)
```

## Token classification (first hit wins)

1. `<project-root>/.scitex/dev/cli-audit-dict.yaml` — project-local dict.
2. `~/.scitex/dev/cli-audit-dict.yaml` — user dict.
3. Bundled catalog from [06_noun-verb-catalog.md](06_noun-verb-catalog.md).
4. Moby POS dictionary (~130k English words, vendored ~900 KB gzipped).
5. Otherwise → warning to extend the custom dict.

## What it flags (warn-only)

- §1 leaf token is a noun without a verb (`<cli> dashboard` → suggests `start-dashboard`).
- §1 bare transitive verb at top level (`<cli> list` → demands `list-<object>`).
- §1 group (non-leaf) token is a verb (groups must be nouns).
- §1a missing introspection commands (`list-python-apis`, `mcp list-tools`) and their `--json` flag.
- §1b banned bare leaves (`version`, `completion`).
- §1d tokens not in catalog/dict/Moby.
- §2 missing universal flags at top: `--version`/`-V`, `--help-recursive`, **`--json`** (so `<cli> --json` parses without crashing); on read verbs: `--json`; on mutating verbs: `--dry-run` and `--yes`/`-y`.
- §4 missing concrete example in command help/epilog (Click guarantees the Usage line).
- §10 CLI startup speed — `import <top-level-module>` cold-start exceeds 500ms. Click runs the program once per Tab press; slow import = unusable tab-completion. Remediation: PEP 562 lazy `__getattr__` in `__init__.py` (see python-api skill 04 "PEP 562 module __getattr__" section).

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
| §2   | Universal flag presence                      | yes       | Root: `--version`/`-V`, `--help-recursive`, `--json` (parseable). Leaves: `--json` on read verbs; `--dry-run` and `--yes`/`-y` on mutating verbs. |
| §3   | Exit code conformance                        | partial   | Top-level bogus-flag returns 2 (behavioral; `--behavioral`).         |
| §4   | Help format                                  | partial   | Heuristic: looks for "example", "$ ", or "e.g." in help/epilog.      |
| §5   | Deprecation hard-error redirect              | no        | Renamed commands are typically `hidden=True`; auditor skips them.    |
| §6a  | Env var prefix `SCITEX_<PKG>_*`              | partial   | Static source scan flags bare-pkg prefix; cross-pkg `SCITEX_*` allowed. |
| §6b  | Config path fallback documented in `--help`  | yes       | Greps root help/epilog for `config.yaml`, `$SCITEX_<PKG>_CONFIG`, or `~/.scitex/`. |
| §7   | CLI ↔ MCP parity                             | no        | Could compare `list-python-apis` and `mcp list-tools` output (TODO). |
| §8   | stdout/stderr discipline                     | partial   | `list-python-apis --json` parsed as JSON (behavioral; `--behavioral`). |
| §10  | CLI startup speed (`import <pkg>` < 500ms)   | yes       | Cold-start measurement in fresh subprocess. Threshold: 500ms (Click runs program once per Tab press). Remediation: PEP 562 lazy `__getattr__` in `__init__.py`. |

## Run audit-all periodically during development

Single-leaf check across every auditor (cli, mcp-tools, skills, python-apis, project):

```bash
scitex-dev ecosystem audit-all <distribution>
scitex-dev ecosystem audit-all <distribution> --json --severity error
```

Different from `audit-summary`, which is the **cross-leaf** rollup (every package). Use `audit-all` while editing one package; use `audit-summary` for ecosystem health.

**Recommendation:** wire `audit-all` into a periodic background loop while developing — keeps the regressions you cause immediately visible instead of accumulating until a release. Three flavours:

```bash
# Cron (runs every 10 min while you work)
*/10 * * * * cd ~/proj/<pkg> && scitex-dev ecosystem audit-all $(basename $PWD) >> ~/.scitex/dev/runtime/audit.log 2>&1

# Background loop in a tmux/screen pane (manual)
while sleep 300; do scitex-dev ecosystem audit-all <pkg> --severity error || say "audit failed"; done

# Agentic loop (Claude Code) — `/loop 5m scitex-dev ecosystem audit-all <pkg>`
#   The /loop skill self-paces the cadence and reports drift back to you.
```

The cheap-to-run cases (audit-cli, audit-mcp-tools, audit-skills) finish in under a second on a fast leaf; audit-python-apis and audit-project are the slow ones. Even with all five, total wall-clock is well under 10s for healthy packages.

Periodic invocation also tightens the feedback loop on **§10 (CLI startup speed)** — you'll notice when an `__init__.py` change breaks the < 500ms threshold the same minute you make it, not three releases later.

### `--json` for agentic / programmatic consumers

Every auditor accepts `--json`, and `audit-all --json` returns a structured aggregate so an agent (or any script) can reason about violations without parsing human text:

```bash
scitex-dev ecosystem audit-all <pkg> --json
```

Shape:

```json
{
  "distribution": "scitex-stats",
  "results": {
    "audit-cli":         {"exit": 1, "data": {"package": "...", "violations": [...]}},
    "audit-mcp-tools":   {"exit": 0, "data": {...}},
    "audit-skills":      {"exit": 0, "data": {...}},
    "audit-python-apis": {"exit": 0, "data": {...}},
    "audit-project":     {"exit": 1, "data": {...}}
  }
}
```

Each per-auditor `data.violations` is a list of `{command, rule, message}` objects. Agents writing scitex-* packages should:

1. Run `audit-all <pkg> --json` after every code-shape change (rename, refactor, new command).
2. Parse `results[*].data.violations` and self-correct any rule violations before declaring the change done.
3. Track `results[*].exit` — overall non-zero means at least one auditor flagged something.

The JSON contract is the same across packages so a single agent prompt can audit any leaf:

```python
import json, subprocess
r = subprocess.run(
    ["scitex-dev", "ecosystem", "audit-all", pkg, "--json"],
    capture_output=True, text=True,
)
report = json.loads(r.stdout)
all_violations = [
    (auditor, v)
    for auditor, res in report["results"].items()
    for v in res.get("data", {}).get("violations", [])
]
```

This same pattern works for individual auditors (`scitex-dev ecosystem audit-cli <pkg> --json`) when an agent only needs one dimension.

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
```

## Operational notes

- Run in CI for every `scitex-*` repo.
- Never fails the build, but drift becomes visible.
- Custom dicts are **additive**: they extend the catalog with package-specific tokens, never reclassify or override existing ones. A token already classified by the canonical catalog keeps its class even if also listed in a dict.
