---
description: |
  [TOPIC] Ecosystem Quality Checklist
  [DETAILS] Periodic ecosystem-wide quality checklist, §0-§10 — the observation half: run during `/speak-and-call` passes or manually between release waves. Each section lists what to verify, how to run the check, and the canonical fix — covering the prerequisites/scope gate, repository-level audits (branch hygiene, push state, CI status across all repos), content-level audits (test scope purity, SKILL.md frontmatter completeness, README per-section star ratings, doc-example chain resolution), and automation audits (nightly workflow scheduling, optional-deps hygiene, and the two reporting outputs including the append-only findings log). Acting on the findings — response protocol, do-not-touch guard, and the release-blocking probes §11-§19 — is the sibling `07_release-gate-probes.md`. Use as the strategic runbook when the ecosystem feels off, after a release wave, or on a fixed cadence.
tags: [scitex-general-quality-checklist]
---

# SciTeX Ecosystem — Periodic Quality Checklist

Run during `/speak-and-call` passes or manually. Each section lists
what to verify, how, and the canonical fix. Keep the check cheap —
delegate big ones to subagents.

**Section groups** (this leaf — the observation half):

- **§0** Prerequisites & scope gate
- **§1–§3 — Repository-level audits** (branch, push, CI)
- **§4–§7 — Content-level audits** (test scope, SKILL.md, README callout, doc chains)
- **§8–§10 — Automation audits** (nightly schedule, deps, reporting)

Acting on what a pass finds — response protocol, do-not-touch guard, and the
release-blocking probes (§11–§19) — is [07_release-gate-probes.md](07_release-gate-probes.md).
Failure-mode cookbook: [01_failure-playbook.md](01_failure-playbook.md) (triage
table; recipes in `05_packaging-…` and `06_compat-and-refactor-drift.md`).

## 0. Prerequisites

- `gh auth status` succeeds; `$HOME/proj/scitex-*` present;
  `gh`/`git -C`/`pip` on PATH.
- Never touch user uncommitted edits (`git -C <path> status --short`);
  only stage files YOU modified. Bypass X11 pre-push hook with
  `-c core.hooksPath=/dev/null`.

**Scope** = has `pyproject.toml` AND directory name == pyproject `name`
(filters paper/template repos like `scitex-paper-1st/` that vendor
`name = "scitex-writer"`):

```bash
name=$(grep -oP '^name\s*=\s*"\K[^"]+' "$p/pyproject.toml" | head -1)
[ "$name" = "$(basename $p)" ] || continue
```

Or use an explicit allowlist — see `audit_english_only.py`.

## 1. Branch hygiene (every repo on `develop`)

Every in-scope repo on `develop`, ahead-of-or-equal `main`:

```bash
for p in $HOME/proj/scitex-*; do
  br=$(git -C "$p" rev-parse --abbrev-ref HEAD 2>/dev/null) || continue
  [ "$br" != "develop" ] && echo "ANOMALY: $(basename $p) on $br"
done
```

Fix: fast-forward develop via `git update-ref` (avoids checkout on
dirty tree), push, delete feature branch. If no `develop`:
`git checkout -b develop main; git push -u origin develop`.

## 2. Push state

No unpushed commits: `git -C "$p" log "origin/$br..$br" --oneline` →
empty. If ahead, push (`-c core.hooksPath=/dev/null` bypasses X11 hook).
Never force-push shared branches.

## 3. CI green (per repo, latest run on develop)

**Check:** `gh run list --repo ywatanabe1989/<pkg> --branch develop --limit 1`.
Flag `failure`, `cancelled`, `in_progress > 1h`.

Severity: **CRITICAL** blocks release; **HIGH** one pkg; **MEDIUM**
test bug; **LOW** cosmetic. Full cookbook (~18 patterns): triage table in
[01_failure-playbook.md](01_failure-playbook.md), recipes in
[05_packaging-and-release-failures.md](05_packaging-and-release-failures.md) and
[06_compat-and-refactor-drift.md](06_compat-and-refactor-drift.md).

## 4. Test scope purity

Leaf packages (scitex-io, scitex-stats, etc.) MUST NOT import the
`scitex` umbrella in their tests — only in `scripts/` or `examples/`.
Cross-**scitex**-package imports use `pytest.importorskip` so a clean
sibling-less venv still collects.

> Optional 3rd-party deps that power *this* package's own feature
> (e.g. `fastmcp` for a package's own MCP server) follow the opposite
> rule: include them in `[dev]` and run the tests unconditionally. The
> full boundary lives in
> [01_ecosystem/02_dependency-and-version-pinning.md `[dev]` extras
> completeness](../01_ecosystem/02_dependency-and-version-pinning.md).

**Check:** `scripts/audit_test_scope.py --projects-root $HOME/proj` in
scitex-python. Reports every test-level `import scitex` / bare sibling.

> Canonical: `scitex-dev/scripts/quality/audit_test_scope.py` (mirrored
> to `scitex-python/scripts/`). Prefer
> `python -m scitex_dev._cli_quality audit_scope --projects-root $HOME/proj`.

## 5. SKILL.md frontmatter completeness

Every `scitex-*/src/scitex_*/_skills/<pkg>/SKILL.md` must carry:

```yaml
name: <pkg>
description: <one-sentence trigger with drop-in replacement>
primary_interface: python | cli | mcp | hook | mixed
interfaces: {python: 0..3, cli: 0..3, mcp: 0..3, skills: 0..3, hook: 0..3, http: 0..3}
```

Body starts with a one-line description (no blockquote callout). The
old `> **Interfaces:** ...` summary line is **deprecated** as of 2026-05
— star ratings now live on each interface section header (see §6).

**Check:** glob all SKILL.md, parse frontmatter, report missing fields;
warn on any surviving `> **Interfaces:**` callout line.

## 6. README per-section star ratings

Every `scitex-*/README.md` puts the interface star rating directly on
each interface section header, not in a separate summary callout:

```markdown
## Python API ⭐⭐⭐
## CLI Commands ⭐
## MCP Server ⭐⭐
## Skills ⭐⭐
```

Strip parenthetical expansions (`(Application Programming Interface)`)
and trailing role descriptors (`-- for AI Agents`, `— for AI Agent
Discovery`). Also: do not duplicate the badges block — keep one
`<!-- scitex-badges:start --> ... :end -->` block at the top, no
secondary `<p align="center">` badge row under the logo.

## 7. Doc-example chains resolve

Every `stx.X.Y.Z` chain in READMEs / docs/*.md must resolve against the
installed scitex API:

```
python3.11 scripts/audit_doc_examples.py --projects-root $HOME/proj
```

On failure: (a) install the missing downstream in the workflow, or (b)
fix the docstring chain.

> Canonical: `scitex-dev/scripts/quality/audit_doc_examples.py` (mirrored
> to `scitex-python/scripts/`). Prefer
> `python -m scitex_dev._cli_quality audit_docs --projects-root $HOME/proj`.

Line-limit auditor: `scitex-dev/scripts/quality/audit_line_limits.py`
(mirrored), allowlist `line_limits_allowlist.txt` alongside.

## 8. Nightly workflows are scheduled

Every package test workflow should run daily (07:00 UTC) and support
`workflow_dispatch`:

```yaml
on:
  push: {branches: [develop, main]}
  schedule:
    - cron: "0 7 * * *"
  workflow_dispatch:
```

## 9. Optional-deps hygiene

- Leaf pkgs keep a minimal default install; heavy deps go in
  `[project.optional-dependencies]`.
- Every package defines an `[all]` extra (may be empty for utilities).
- Consumers of scitex pkgs pin min version in their pyproject (see
  `01_ecosystem/02_dependency-and-version-pinning.md`).

## 10. Reporting back

Two outputs per pass.

### 10a. Current-state table (for the human)

`| package | branch | push | CI | notes |` — anomalies only. Verify
each finding (no false positives). Mark pre-existing test-debt as such.

### 10b. Append-only audit log (for regression tracking)

Append one entry per pass to `scitex-dev/quality-audits/YYYY-MM-DD.md`
(top-level, not `logs/` which is gitignored):

```markdown
## YYYY-MM-DD HH:MM UTC — /speak-and-call pass

- Fixes applied:
  - <pkg>: <one-line fix> (<commit-sha>)
- Outstanding (flagged for user):
  - <pkg>: <one-line blocker>
- Next scheduled check: <ScheduleWakeup delay / cron>
```

Makes multi-week trends legible ("audio fails same way 3/7" → systemic).

