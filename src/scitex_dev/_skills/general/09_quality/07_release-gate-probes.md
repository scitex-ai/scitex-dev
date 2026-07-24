---
description: |
  [TOPIC] Release-gate probes and audit response protocol
  [DETAILS] The acting half of the ecosystem quality checklist (§11-§19): the /speak-and-call response protocol, the do-not-touch guard for dirty trees with its mandatory commit wrapper, and the standing invariants each of which is a declared release blocker - extras-completeness so every canonical package is reachable, env-var documentation completeness, dynamic audit via agent task execution (planned), dashboard export, English-only enforcement, AGPL-3.0-only license enforcement, and the ten release-gate questions. The observation half - what to check and how - is the sibling `02_checklist.md`. Use before shipping, or when deciding whether a pass may touch a repo at all.
tags: [scitex-general-quality-release-gate-probes]
---

# SciTeX Ecosystem — Release-Gate Probes and Response Protocol

Companion to [02_checklist.md](02_checklist.md), which covers §0–§10: what a
periodic pass *observes*. This leaf covers what it may *do* about it.

Two things live here, and they share one property — each decides an
**authorisation**, not a measurement:

- **§11–§12 — may I act?** The response protocol for a `/speak-and-call` run,
  and the do-not-touch guard that keeps a pass out of a tree holding
  uncommitted user work.
- **§14–§19 — may I ship?** Standing invariants over the whole ecosystem, each
  stated as a release blocker rather than a warning, closing with the ten
  release-gate questions.

Section numbers are the checklist's originals (there is no §13), so any
cross-reference elsewhere in the tree still resolves.

## 11. Response protocol for a /speak-and-call quality run

1. Branch + push audit (§1, §2) — anomalies only.
2. CI audit (§3) — table of failing runs + canonical fix.
3. Apply fixes to non-dirty repos; report dirty ones separately.
4. `ScheduleWakeup` 270–900 s for CI to rerun; no tight polling.
5. Summary: X/N green, Y needs user, Z in progress.
6. Append entry to `scitex-dev/quality-audits/YYYY-MM-DD.md` (§10b).

## 12. Do-not-touch list (refresh every run)

Never modify a repo with uncommitted user work. Run
`git -C <path> status --short` each pass. For issues in dirty trees:
prefer GH-API merge, `git worktree add`, or report commands. Never
stash/pop.

Commit-in-dirty-tree guard (mandatory):

```bash
~/.claude/to_claude/bin/git_guard_commit.sh --repo <abs-path> \
    <file1> [...] -- -m "msg"
```

Aborts if index has extras. Prevents the 2026-04-24 accident (commit
swept 40 pre-staged user files). Home: `~/.claude/to_claude/bin/`.

## 14. Extras-completeness (every canonical package reachable)

Stricter than playbook §6 (which only catches `foo = []` when
`src/scitex/foo/` exists). Every canonical ecosystem package MUST appear
in at least one named extra AND in `[all]`, so
`pip install scitex[<name>]` actually pulls `scitex-<name>`.

**Failure (2026-04-24).** `clew = []`, `path = ["GitPython","matplotlib"]`
(no `scitex-path`), `ui = []`, `linter`/`core`/`scholar` absent.
`pip install scitex[path]` installs GitPython but NOT `scitex-path`, so
`stx.path.find_git_root()` silently falls back to the umbrella shim
instead of the standalone's full implementation. Rule:
`01_ecosystem/03_modules-and-standalone-packages.md` §8.

**Probe (uses canonical registry):**

```bash
python3.11 - <<'EOF'
import subprocess, json, tomllib
reg = json.loads(subprocess.check_output(
  ["scitex","dev","ecosystem","list","--json"]))["packages"]
non_lib = {"pip-project-template","singularity-template",
  "automated-research-demo","scitex-research-template","scitex"}
libs = sorted(p for p in reg if p not in non_lib)
ex = tomllib.loads(open("pyproject.toml","rb").read()
  )["project"]["optional-dependencies"]
m_any = [p for p in libs if not any(p in ex.get(e,[]) for e in ex)]
m_all = [p for p in libs if p not in ex.get("all", [])]
if m_any: print("MISSING any extra:", m_any); raise SystemExit(1)
if m_all: print("MISSING [all]:", m_all); raise SystemExit(1)
print("OK:", len(libs), "ecosystem pkgs reachable")
EOF
```

**Fix.** Add missing entries. TS-only modules (`ui`) either declare the
pypi package OR raise an explicit ImportError from the shim (see `09`
§12). Never merge pyproject changes that leave a canonical pkg
unreachable.

## 15. Env-var documentation completeness

Every package that reads one or more `SCITEX_*` env vars MUST carry an
`NN_env-vars.md` leaf under `src/<pkg_snake>/_skills/<pkg>/` that documents
each variable (purpose, default, type, opt-in vs opt-out). Rule defined in
`01_ecosystem/04_environment-variables.md`.

**Probe** (diff source vs docs across the ecosystem):

```bash
for p in $(scitex dev ecosystem list --json | python3 -c "import sys,json; d=json.load(sys.stdin); print(' '.join(x for x in d['packages'] if not x.endswith('template') and x!='scitex' and x!='automated-research-demo'))"); do
  src_envs=$(grep -rhoE 'SCITEX_[A-Z0-9_]+' $HOME/proj/$p/src/ 2>/dev/null | sort -u | wc -l)
  docs_envs=$(grep -rhoE 'SCITEX_[A-Z0-9_]+' $HOME/proj/$p/src/*/_skills/$p/*.md 2>/dev/null | sort -u | wc -l)
  [ "$src_envs" -gt 0 ] && [ "$docs_envs" -lt "$src_envs" ] && echo "$p: $docs_envs/$src_envs documented"
done
```

Any non-empty line is a release blocker — create/augment the leaf, link it
from `SKILL.md`, commit as `docs(env-vars): document SCITEX_* variables
actually read by <pkg>`.

## 16. Dynamic audit via agent task execution (planned)

Static = "looks right"; dynamic = "works right" under realistic
workloads (agents on end-to-end tasks, logging tool-use + output
quality). Static pass (§§1–15 + playbook §98) gates commit; dynamic
additionally gates PyPI release.

Design: `scitex-dev/src/scitex_dev/_skills/scitex-dev/20_dynamic-audit.md`
(tasks T01–T10; 3-task first pass). Host: `scitex-dev` owns
`scripts/quality/` + `logs/quality-audits/`; `scitex-python/scripts/`
is a mirror.

## 17. Dashboard export

`python3.11 ~/proj/scitex-python/scripts/audit_quality_dashboard.py` →
`scitex-dev/dashboards/quality.md`. Scope = §0 ∩ (`scitex*` or
allowlist: figrecipe, socialia, openalex-local, crossref-local).

## 18. English-only enforcement

Exempt with `# i18n-ok` / `<!-- i18n-ok -->` (±2-line marker).
`python3.11 ~/proj/scitex-python/scripts/audit_english_only.py`.

## 19. License enforcement (AGPL-3.0-only)

SPDX `license = "AGPL-3.0-only"` + AGPL classifier + LICENSE at root.
`scitex-dev/scripts/quality/audit_license.py` (+ `fix_license.py
--apply --commit`; skips dirty trees).

## Release-gate questions

1. Useful for Ph.D. students/researchers?
2. Meaningful tests, all green?
3. Easy to understand for humans and AI?
4. Easy to use for humans and AI?
5. Easy to maintain?
6. Docs / Read the Docs / examples in sync with code?
7. Periodic quality check actually running?
8. SciTeX conventions followed throughout?
9. All packages standardized and consistent?
10. English-only in comments and docs?
