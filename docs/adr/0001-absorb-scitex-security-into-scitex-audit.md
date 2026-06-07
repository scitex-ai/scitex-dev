# ADR-0001: Absorb scitex-security into scitex-audit

## Status

Proposed (2026-06-07) — awaiting lead sanity-check before any code change.

## Context

The SciTeX ecosystem currently ships two thematically overlapping security
packages:

| Package | PyPI version | Description | Public API surface |
| --- | --- | --- | --- |
| `scitex-security` | 0.1.4 (Alpha) | "GitHub security alerts checker (Dependabot, secret scanning, code scanning) — standalone module from the SciTeX ecosystem" | `check_github_alerts`, `save_alerts_to_file`, `get_latest_alerts_file`, `format_alerts_report`, `GitHubSecurityError` (5 symbols) |
| `scitex-audit` | 0.1.7 (Alpha) | "Unified security scanning by orchestrating bandit, shellcheck, pip-audit, and GitHub alerts" | `audit(path, checks, output_file) → dict` (1 symbol) |

Both are AGPL-3.0, both `Development Status :: 3 - Alpha`. Both were
registered in the ecosystem registry on 2026-06-07 by PR #133
(`feat(ecosystem): split registry + add scitex-audit/core/math/linter`).

### Audit of the current coupling

Reverse-direction import scan across `~/proj` (per ecosystem skill
`03_modules-and-standalone-packages.md` §1):

```bash
$ rg -n 'from scitex_security|import scitex_security' --type py ~/proj
```

| Consumer | File | Lines | Notes |
| --- | --- | --- | --- |
| **scitex-audit** | `src/scitex_audit/_github.py` | 83-84 | `from scitex_security import GitHubSecurityError, check_github_alerts` — **inside a `try/except ImportError` block**; standalone-mode fallback uses `gh` CLI directly. Soft consumer, no flag-day. |
| scitex-python umbrella | `src/scitex/cli/_lazy_subcommands.py` | 81 | Generic `("cli", "main")` shape matcher — not a hard import of `scitex_security`. Unaffected. |
| scitex-security itself | `src/scitex_security/{__init__.py,__main__.py,cli.py,_skills.py}`, `tests/`, `examples/`, `docs/sphinx/conf.py`, `scripts/verify_runtime_path.py` | various | All internal — would move with the absorption. |
| `legacy/scitex-audit/` (older clone) | `src/scitex_audit/_github.py:83-84` | same as live scitex-audit, kept as-is until retirement |
| PyPI-installed dep (`scitex-plt/.venv/.../scitex_security/__init__.py`) | venv mirror | irrelevant to source migration |

**Net external consumer count: ONE** — scitex-audit, and it already
treats `scitex_security` as optional.

### What scitex-audit's `_github.py` actually does

scitex-audit 0.1.7 carries TWO paths in `run_github_check()`:

```python
try:
    from scitex_security import GitHubSecurityError as _GSE
    from scitex_security import check_github_alerts
    # … use the helper
except ImportError:
    # Standalone mode: use gh CLI directly
    alert_types = {
        "dependabot": "dependabot/alerts?state=open",
        "code-scanning": "code-scanning/alerts?state=open",
        "secret-scanning": "secret-scanning/alerts?state=open",
    }
    # … same logic, inlined
```

So scitex-audit **already has the logic** inlined as a fallback. The
scitex-security path is a thin compatibility wrapper, not a hard
dependency that buys behaviour.

### Why this is an absorption candidate (skill `03` §1 test)

The "when to keep a standalone" rule reads:

> Standalone package iff **zero scitex deps + heavy standalone value**.

- ✅ scitex-security has zero scitex deps (only `click>=8.0`).
- ❌ scitex-security does **not** have heavy standalone value:
  - Scope = strict subset of scitex-audit ("GitHub alerts" ⊂ "Unified
    security scanning incl. GitHub alerts").
  - 5 public symbols, ~6 source files including `__init__`/`__main__`.
  - The one external caller (scitex-audit) treats it as optional.
  - The 0.1.4 Alpha version reflects low downstream adoption.

The zero-scitex-deps test alone doesn't preserve a standalone — the
standalone-value test must also pass. Here, it doesn't.

### Why NOT absorb (the counter-argument)

| Argument | Verdict |
| --- | --- |
| "scitex-security is zero-dep so users on a tiny footprint can install just it." | Weak — scitex-audit is also nearly zero-dep at runtime (calls bandit/shellcheck/pip-audit/gh via subprocess; only ships the orchestrator). A user wanting only GH-alerts can `pip install scitex-audit` and invoke `audit(checks=["github"])`. |
| "scitex-security has a separate CLI (`scitex-security`) some scripts depend on." | Manageable — scitex-audit can register a `scitex-security` console-script alias as part of the absorption, or we keep a deprecated CLI bridge for one release. |
| "Different `requires-python` floors (security ≥ 3.9 vs audit ≥ 3.10)." | scitex-audit's floor wins post-absorption (3.10). Acceptable per ecosystem floor (registry packages mostly ≥ 3.10 already). |
| "scitex-security might grow non-GitHub scanners (e.g. local secret-grep)." | Speculative; no current roadmap. If it grows that way later, the right answer is a `scitex_audit.secrets` submodule, not a separate package. |

Conclusion: **no surviving reason to keep them split**.

## Decision

**Absorb `scitex-security` into `scitex-audit`**, with a thin
re-export bridge during transition and a one-release-wave consumer
migration. scitex-security 0.2.0 becomes a deprecated alias package
that re-exports from `scitex_audit.github`; the registry archives it
in the same wave that scitex-audit 0.2.0 ships.

### Placement / design principles

1. **One owner per concern.** "GitHub security alerts" belongs to the
   scitex-audit security-scanning concern, not its own package. Skill
   `03` §1 rules out the standalone since the standalone-value test
   fails.
2. **No flag-day.** Bridge pattern from skill `05` keeps the
   `scitex_security.*` import path resolving for one release after the
   move, so the single external consumer (scitex-audit's own
   `_github.py`) keeps working unmodified. We delete the bridge once
   consumers are migrated (same wave — there's only one).
3. **No deprecation tombstones.** Per ecosystem deprecation policy,
   the migration commits in `scitex-audit` land in the same wave as
   the scitex-security thin-shim release — callers don't need to
   write transitional `if available:` shims.
4. **Registry honesty.** scitex-security drops from
   `ECOSYSTEM_IMPORTS_TO_DIST` and the registry gains `archived=True`
   (same pattern as scitex-linter in #133) so audit-all and umbrella-
   extras reconciliation correctly stop expecting a standalone.
5. **Bridge style — explicit named re-exports** (scholar pattern
   from skill `05` §"Concrete pattern"). The public surface is 5
   symbols and grep-able; deep submodule paths are not used by any
   external caller, so `sys.modules` aliasing is unnecessary.

### Inventory — what moves and where

| Source (`scitex-security`) | Symbol / module | Target (`scitex-audit`) | Notes |
| --- | --- | --- | --- |
| `src/scitex_security/github.py` | `check_github_alerts` | `src/scitex_audit/github.py` (NEW public submodule) | Replaces the inlined fallback in `_github.py`; the existing `_github.py` orchestrator delegates to `scitex_audit.github.check_github_alerts`. |
| `src/scitex_security/github.py` | `save_alerts_to_file` | `scitex_audit.github` | — |
| `src/scitex_security/github.py` | `get_latest_alerts_file` | `scitex_audit.github` | — |
| `src/scitex_security/github.py` | `format_alerts_report` | `scitex_audit.github` | — |
| `src/scitex_security/github.py` | `GitHubSecurityError` | `scitex_audit.github` | Existing scitex-audit `GitHubSecurityError` in `_github.py` becomes a re-export from `scitex_audit.github` (single SSOT). |
| `src/scitex_security/cli.py` | `scitex-security` console script | `scitex_audit.github_cli:main` + entry-point `scitex-security` re-registered from scitex-audit | Keeps the user-facing CLI name working. Or: drop & document the rename to `scitex-audit github`. Decision deferred — flag for lead. |
| `src/scitex_security/_paths.py` | `PKG_SHORT`, `get_default_alerts_dir` | `scitex_audit/_paths.py` | Adjust `PKG_SHORT = "audit"`; the user-facing default alerts dir migrates from `~/.scitex/security/` → `~/.scitex/audit/github-alerts/`. Add a one-shot migration helper. |
| `src/scitex_security/_skills/` | skills docs | `scitex_audit/_skills/scitex-audit/` | Merge into the existing skills dir; renumber to avoid collisions. |
| `src/scitex_security/__init__.py` | top-level `__all__` | scitex-security 0.2.0 shim only | The new shim does `from scitex_audit.github import …` + matching `__all__`. |

### Per-step recipe (phased rollout)

**Phase 0 — Plan ratification (this ADR).**
- Lead reviews the plan; flags symbol-rename concerns, the
  `scitex-security` CLI fate, and the `~/.scitex/security/` →
  `~/.scitex/audit/github-alerts/` path migration.
- Once accepted, this ADR moves from `Proposed` → `Accepted (YYYY-MM-DD)`
  and we proceed.

**Phase 1 — scitex-audit publishes the absorbed module.**
- In `scitex-audit`: add `src/scitex_audit/github.py` with the 5
  public symbols, ported verbatim from `scitex_security/github.py`.
- Update `src/scitex_audit/__init__.py` to expose the public surface:
  `from .github import check_github_alerts, save_alerts_to_file,
  get_latest_alerts_file, format_alerts_report, GitHubSecurityError`
  + matching `__all__` extension.
- `_github.py` (the orchestrator) drops its inlined gh-CLI fallback
  and delegates to `scitex_audit.github.check_github_alerts`.
- Add an optional console-script `scitex-audit-github = "scitex_audit.github_cli:main"`
  (decision flagged to lead — keep `scitex-security` name or rename).
- Release as `scitex-audit==0.2.0`.

**Phase 2 — scitex-security becomes a thin shim release.**
- In `scitex-security`: replace `github.py` and `cli.py` with thin
  re-exports from `scitex_audit.github`. Bump dep:
  `scitex-audit>=0.2.0`. Add a `DeprecationWarning` at import time:
  *"scitex-security has been absorbed into scitex-audit. Install
  `scitex-audit` directly; this package will be removed in a future
  release."*
- Release as `scitex-security==0.2.0`.
- README updated to point to scitex-audit.

**Phase 3 — scitex-dev ecosystem reconciliation.**
- Drop `"scitex_security": "scitex-security"` from
  `ECOSYSTEM_IMPORTS_TO_DIST` in
  `src/scitex_dev/_ecosystem/_release/pyproject_lint.py`.
- Set `archived=True` on the `scitex-security` entry in
  `src/scitex_dev/_ecosystem/_registry.py` (same pattern as
  scitex-linter in #133). Comment block records the absorption
  ADR-0001 reference.
- Update umbrella shim `scitex-python/src/scitex/security/__init__.py`
  to re-export from `scitex_audit.github` (the umbrella's
  `[security]` extra now installs `scitex-audit`, not
  `scitex-security`).
- Audit `~/proj/scitex-python/pyproject.toml` `[project.optional-dependencies]`:
  swap `security = ["scitex-security"]` → `security = ["scitex-audit"]`.
  Verify per skill `03` §8 — every ecosystem package has a matching
  extra that installs it.

**Phase 4 — Consumer migration.**
- The single hard consumer (scitex-audit's own `_github.py`) is
  already updated in Phase 1 — no other consumer migration needed.
- scitex-python umbrella ships in the next release wave; users who
  `pip install scitex[security]` then transparently get scitex-audit.
- Document the migration in `scitex-audit`'s CHANGELOG and the
  scitex-dev `_skills/general/01_ecosystem/05_re-export.md` skill
  references the absorption as a worked example.

**Phase 5 — Bridge sunset (one release later).**
- After Phase 4 ships, the next ecosystem-version reconciliation
  wave (`scitex-dev ecosystem reconcile-versions`) confirms zero
  active downstream pins on `scitex-security`. At that point a
  follow-up PR removes the scitex-security 0.2.0 shim and yanks the
  PyPI package as a final step. (We *can* keep the deprecated shim
  indefinitely if there's a long-tail PyPI user — judgement call at
  that future review.)

### Release wave summary

| Wave | Packages | What changes |
| --- | --- | --- |
| **W1** (this PR's outcome) | `scitex-audit 0.2.0`, `scitex-security 0.2.0`, `scitex-dev` (registry + pyproject_lint + skills doc), `scitex-python` (umbrella extras + bridge module) | Absorption lands; bridge keeps callers green. |
| **W2** (next regen sweep) | `scitex-dev` ecosystem-version reconciliation bumps minima across registered consumers | Single-consumer rule means this is essentially a no-op for security; primary value is the registry/CHANGELOG record. |
| **W3** (~1 release later) | optional `scitex-security` PyPI yank | Only if PyPI dist statistics show zero active downloads. |

### What this ADR does NOT decide

- The fate of the `scitex-security` PyPI name post-shim (yank vs. keep
  the deprecated alias forever). Re-evaluated at W3.
- Whether `~/.scitex/security/` path migration is automatic
  (one-shot `_paths.py` symlink) or manual (release note). Flagged
  for lead.
- Whether the `scitex-security` console script keeps its name or
  becomes `scitex-audit github`. Flagged for lead.

## Consequences

**Positive**
- One package owns "ecosystem security scanning"; CLI / docs / skills
  surface is unified.
- Ecosystem-wide audit-all and umbrella-extras reconciliation stop
  drift-chasing a standalone whose only consumer is also in-ecosystem.
- The "soft" `try/except ImportError` coupling in scitex-audit's
  `_github.py` becomes a hard, typed, tested integration.
- Fewer PyPI releases to keep version-aligned in the next
  reconcile-versions wave.

**Negative / cost**
- One package (`scitex-security`) becomes a thin deprecated shim for
  at least one release wave. Adds a `DeprecationWarning` paper-cut
  for anyone with an `import scitex_security` somewhere outside this
  repo set. Survey didn't find any such caller; risk is bounded.
- `~/.scitex/security/` users (if any) need the alerts directory
  remapped to `~/.scitex/audit/github-alerts/`. Mitigated by a
  one-shot symlink in `_paths.py` migration helper.
- The `scitex-audit` package gains a `[github]` concern (CLI script,
  alerts dir, the 5 public symbols) — net more API surface in one
  place, which is the whole point but worth flagging.
- requires-python bumps from 3.9 (scitex-security) to 3.10
  (scitex-audit) for the absorbed callers — acceptable per current
  ecosystem floor.

**Avoided cost (vs. status quo)**
- Two `_skills/` dirs ⇒ one. Two CLI surfaces ⇒ one. Two PyPI release
  cadences ⇒ one. Two sphinx builds ⇒ one. Two readme-trees pointing
  at each other ⇒ one.

## Notes

- Provenance: lead-assigned task on 2026-06-07 following the
  scitex-audit registry addition in PR #133. Operator referenced the
  plan in a Telegram thread on 2026-06-07 02:56–04:02 JST.
- Skill references:
  `~/proj/scitex-dev/src/scitex_dev/_skills/general/01_ecosystem/03_modules-and-standalone-packages.md`
  (when-to-merge-back §1, dot-scitex layout §6, every-module-has-an-
  extra §8) and
  `~/proj/scitex-dev/src/scitex_dev/_skills/general/01_ecosystem/05_re-export.md`
  (explicit-named-re-export pattern, sys.modules-aliasing alternative,
  release-gate check).
- Related ADR: none in scitex-dev/docs/adr yet (this is 0001). The
  scitex-linter retirement in PR #133 used the `archived=True`
  registry flag without an ADR; ADR-0001 establishes the absorption
  pattern that future "scitex-X ← scitex-Y" decisions can reference.
- Repo links:
  - scitex-audit: https://github.com/ywatanabe1989/scitex-audit (0.1.7, AGPL-3.0)
  - scitex-security: https://github.com/ywatanabe1989/scitex-security (0.1.4, AGPL-3.0)
  - Registry: `src/scitex_dev/_ecosystem/_registry.py` lines 217-228 (audit), 577-583 (security)
- Open questions for lead sanity-check (in priority order):
  1. CLI fate: keep `scitex-security` console-script name (alias to
     scitex-audit) vs. rename to `scitex-audit github`?
  2. `~/.scitex/security/` path migration: auto-symlink in
     `_paths.py` vs. release-note-only?
  3. PyPI `scitex-security` long-term: yank at W3, or keep the
     deprecated shim indefinitely as a courtesy alias?
