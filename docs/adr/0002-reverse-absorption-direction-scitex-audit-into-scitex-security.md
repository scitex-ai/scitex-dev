# ADR-0002: Reverse absorption direction — absorb scitex-audit into scitex-security

## Status

Proposed (2026-06-07) — awaiting lead sanity-check before any code change.

Supersedes ADR-0001 (`docs/adr/0001-absorb-scitex-security-into-scitex-audit.md`).

## Context

ADR-0001 (Accepted 2026-06-07 morning) absorbed `scitex-security` into
`scitex-audit`. W1 execution shipped that direction successfully:
`scitex-audit 0.2.0` is live on PyPI, the registry archive of
`scitex-security` (#141) merged, and the umbrella `[security]` repoint
(#322) merged. Only the final step — publishing `scitex-security 0.2.0`
as the deprecated shim (#12) — was held mid-wave when the operator
questioned the **direction** of the absorption.

The operator's call (2026-06-07 afternoon JST): **reverse it**.
`scitex-security` should be the canonical survivor name; `scitex-audit`
should become the deprecated shim. Rationale (verbatim):

> "Security" is the better unified package name — broader concept,
> consistent with how downstream users think about the surface (GitHub
> alerts + bandit + shellcheck + pip-audit are all *security* concerns).
> "Audit" is the broader codebase but the narrower, more ambiguous
> name (audit = financial audit? code audit? auditing in general?).

The technical inventory in ADR-0001 §Context (single soft consumer, zero
external standalone-value at the security side, etc.) still holds —
those facts are direction-independent. What flips is the **naming**:
the unified package gets the `scitex-security` name, not `scitex-audit`.

### Half-shipped state to recover from

| Asset | State after ADR-0001 W1 | Reversal action |
| --- | --- | --- |
| `scitex-audit 0.2.0` on PyPI | LIVE — published 2026-06-07T09:24Z | **NOT yanked.** Yanks break installed callers and are messy. The 0.2.0 release stays on PyPI as historical. The NEXT scitex-audit version flips its role to a thin shim. |
| `scitex-audit` GH `main` | Has the absorbed `scitex_audit.github` module + `_paths` + CLI + `__main__` + tests | The NEXT version reverses this: re-exports from `scitex_security` + hard-error CLI redirect. |
| `scitex-security 0.2.0` PR (#12) | Open, on HOLD — was going to be the deprecated shim | **Close.** The 0.2.0 number is now reserved for the absorbing release (see below). Reopen as a new PR landing the absorption. |
| `scitex-security 0.1.4` on PyPI | LIVE since May | Unchanged — the next published version flips it to the unified survivor. |
| `scitex-dev` registry archive (#141) | MERGED to `develop` — `scitex-security` marked `archived=True` | **Reverse.** A new PR un-archives `scitex-security` and archives `scitex-audit` instead. |
| `scitex-python` umbrella (#322) | MERGED — `[security] = ["scitex-audit>=0.2.0"]`, `[audit] = ["scitex-audit==0.2.0"]`, `LazyModule("security", external="scitex_audit.github")`, alias-map `"security": "scitex_audit.github"` | **Reverse.** A new PR re-points `[security]` and `[audit]` to `scitex-security`, switches the LazyModule + alias-map back to `scitex_security`. |
| `~/.scitex/audit/github-alerts/` auto-symlink shipped in scitex-audit 0.2.0 | Was the forward-migration target; will exist on any user who imported scitex-audit 0.2.0. | **Reverse-migrate.** scitex-security NEXT detects `~/.scitex/audit/github-alerts/` on first import and symlinks it BACK to `~/.scitex/security/runtime/` (mirror of the 0.2.0 migration, opposite direction). Marker file prevents loops. |
| ADR-0001 file on `origin/docs/adr-absorb-security` | Dangling branch — never merged to develop or main | **Bring into develop** as `Superseded by ADR-0002`, per the ADR skill ("reverse via a new ADR, never edit the superseded one"). |

### Per-repo gh-CLI cwd-detect lesson (carry-over from W1)

Three of W1's PRs (#23 on scitex-audit, #139 + #140 on scitex-dev) were
misfired because `gh pr create` auto-detected the head from the cwd's
git branch instead of using the feature branch I had pushed. Every PR
in the W1-reverse wave must pass `--head <branch>` and `--base <branch>`
explicitly. (Also a post-wave skill-doc task — see §Open follow-ups.)

## Decision

**Reverse the direction.** scitex-security becomes the unified package
that owns both the GitHub-alerts logic AND the audit-orchestrator
(bandit / shellcheck / pip-audit) bodies. scitex-audit becomes the
thin deprecated re-export shim. The release pattern from ADR-0001's W1
is mirrored in reverse — same shape (explicit-named-re-export bridge
per skill 05, hard-error CLI per skill 11, same-wave no-tombstones,
auto-symlink data migration) — but with the roles flipped.

### Placement / design principles

1. **Operator names the canonical package.** The technical inventory
   doesn't dictate which side gets the surviving name; the operator
   does. "scitex-security" wins per his 2026-06-07-afternoon call.
2. **No PyPI yank.** `scitex-audit 0.2.0` is already published; yanking
   creates churn for anyone who installed it. The NEXT scitex-audit
   release becomes a thin shim of scitex-security. Users on 0.2.0
   either pin it (and stay on a soon-to-be-deprecated branch) or
   upgrade and transparently follow the redirect.
3. **Bridge style — explicit named re-exports** (scholar pattern,
   skill 05 §"Concrete pattern"). Identical justification to ADR-0001
   — the public surface is small and grep-able; deep submodule paths
   not used by external callers.
4. **Same-wave consumer migration** (no-tombstones). All internal
   `from scitex_audit.<X>` imports flip to `from scitex_security.<X>`
   in the SAME wave the absorbing release ships. The shim exists only
   for external PyPI users we don't control.
5. **Auto data-dir migration BOTH ways.** `scitex-audit 0.2.0` shipped
   a one-shot `~/.scitex/security/` → `~/.scitex/audit/github-alerts/`
   symlink. `scitex-security` NEXT reverses it: detects
   `~/.scitex/audit/github-alerts/` on first import and symlinks back
   to `~/.scitex/security/runtime/`. Marker files on both sides
   prevent loops.
6. **Registry honesty.** `scitex-security` → `archived=False`,
   `scitex-audit` → `archived=True`. The registry should now reflect
   the post-reversal reality.
7. **Explicit `gh --head <branch> --base <branch>` on every PR.** The
   cwd-detect lesson from W1.

### Locked decisions (mirroring ADR-0001's, role-reversed)

- **CLI rename, hard-error redirect.** The console script becomes
  `scitex-security` (its existing name). `scitex-audit` is the
  hard-error redirect in the NEXT scitex-audit release per skill 11
  §5: prints `error: scitex-audit was unified into scitex-security
  (ADR-0002). Re-run with: scitex-security <verb>`, exits `2`.
- **Auto-symlink.** `~/.scitex/audit/github-alerts/` → `~/.scitex/security/runtime/`
  on first import of `scitex_security` after upgrade. Symlink-preferred,
  move-fallback, marker-gated. No manual user step.
- **No PyPI yank** of scitex-audit 0.2.0. Future versions of scitex-audit
  are deprecated shims.
- **Same-wave no-tombstones** for in-tree callers (#322's umbrella is
  reversed atomically with the security-absorbs-audit release).

### Inventory — what moves and where (reversed from ADR-0001)

| Source (`scitex-audit` post-0.2.0) | Symbol / module | Target (`scitex-security` NEXT) | Notes |
| --- | --- | --- | --- |
| `src/scitex_audit/github.py` | 5 public symbols + 5 internal helpers | `src/scitex_security/github.py` | Identical port. The original came from scitex-security 0.1.4; this is just porting it back to where it now lives. |
| `src/scitex_audit/_runner.py` | `audit(path, checks, output_file)` orchestrator | `src/scitex_security/runner.py` (or absorb into `__init__`) | The unified package now owns the multi-tool security scan. |
| `src/scitex_audit/_bandit.py`, `_shellcheck.py`, `_pip_audit.py`, `_format.py`, `_github.py` | Per-tool runners + result formatter | `src/scitex_security/_bandit.py` (etc.) | Port verbatim; adjust imports `from ._bandit import …` → same path inside scitex_security. |
| `src/scitex_audit/cli.py` + `__main__.py` | Click group with `github check`, `github show-latest`, `skills`, `list-python-apis`, `mcp`, `install-shell-completion`, `print-shell-completion` | `src/scitex_security/cli.py` (extend existing) | scitex-security already has most of this in its 0.1.4 CLI; merge the audit-runner verbs in (e.g. `scitex-security check` for multi-tool, keeping `scitex-security github check` for GH-alerts only). |
| `src/scitex_audit/_paths.py` | `$SCITEX_AUDIT_DIR` + the legacy-security symlink helper | `src/scitex_security/_paths.py` | Use `$SCITEX_SECURITY_DIR` (the original 0.1.4 env var). Add the REVERSE auto-symlink (`~/.scitex/audit/github-alerts/` → `~/.scitex/security/runtime/`). |
| `src/scitex_audit/_skills/scitex-audit/` | Skills docs | `src/scitex_security/_skills/scitex-security/` | Merge into the existing scitex-security skills dir (which is currently being demolished in the on-hold #12 — that demolition gets cancelled). |
| `pyproject.toml`: description, deps | "Unified security scanning by orchestrating bandit, shellcheck, pip-audit, and GitHub alerts" | scitex-security NEXT pyproject | Description updated to reflect the unified scope; deps absorb scitex-audit's. |

### Per-step recipe (phased rollout) — W1-reverse

**Phase 0 — ADR ratification (this file).**
- Lead sanity-checks the reversal plan; flags any of the structural
  decisions (no-yank, version numbering, data-dir migration shape,
  CLI ergonomics) that need re-thinking.
- Status flips `Proposed` → `Accepted (YYYY-MM-DD)` and we proceed.
- Same PR brings `ADR-0001` into `develop` with the Superseded marker
  + `ADR-0002` (this file).

**Phase 1 — `scitex-security` NEXT (the absorbing release).**

Suggested version: **`scitex-security 0.2.0`** (the same number the
on-hold #12 was going to ship; we're reusing it for the absorbing
release instead of the shim release).

- Add `src/scitex_security/{github.py, runner.py, _bandit.py, _shellcheck.py, _pip_audit.py, _format.py, _github.py}` — ported from scitex-audit ≥ 0.2.0.
- Update `src/scitex_security/__init__.py`: expose `audit`, the 5
  GitHub-alerts symbols, and the existing public surface. Keep the
  DeprecationWarning **OUT** of `__init__` (this is now the surviving
  package, not the deprecated one).
- Update `src/scitex_security/cli.py`: extend with audit-runner verbs
  (`scitex-security check` for the multi-tool scan). The existing
  CLI shape (canonical -V / --json / --help-recursive / list-python-apis
  / mcp / skills / completion) stays.
- Update `src/scitex_security/_paths.py`: keep the existing
  `$SCITEX_SECURITY_DIR` semantics. Add `_migrate_legacy_audit_dir()`
  — detects `~/.scitex/audit/github-alerts/` on first import and
  symlinks it back to `~/.scitex/security/runtime/`. Marker-gated.
- `pyproject.toml`: bump `version` to `0.2.0`; description updated to
  match scitex-audit 0.2.0's; absorb any new runtime deps (click is
  already there).
- `CHANGELOG.md`: 0.2.0 section documenting the absorption + the
  ADR-0002 reference + the reversed-from-ADR-0001 history.
- Tests: keep the existing AAA-marked tests; add tests for the new
  absorbed modules; add a `test_paths.py` for the reverse migration.
- **Cancel the on-hold #12** PR — it was going to make scitex-security
  the deprecated shim. Close with a comment pointing at this PR.

**Phase 2 — `scitex-audit` NEXT (the deprecated shim release).**

Suggested version: **`scitex-audit 0.3.0`** (because 0.2.0 is already
on PyPI as the absorbing release we're now reversing).

- Replace the entire `src/scitex_audit/` surface with thin re-exports
  from `scitex_security`:
  - `__init__.py`: `from scitex_security import …` + DeprecationWarning.
  - `github.py`, `runner.py`, etc.: each a thin re-export shim.
  - `cli.py`: hard-error redirect per skill 11 §5. Prints
    `error: scitex-audit was unified into scitex-security (ADR-0002,
    scitex-dev #<PR>). Re-run with: scitex-security <verb>`, exits 2.
  - `__main__.py` keeps the existing `from scitex_audit.cli import main`
    so `python -m scitex_audit` also hard-errors.
- `pyproject.toml`: `version = "0.3.0"`; `Development Status :: 7 - Inactive`;
  `dependencies = ["scitex-security>=0.2.0"]`. Drop click (pulled
  transitively by scitex-security).
- Drop `src/scitex_audit/_skills/` (moved to scitex-security).
- Drop `src/scitex_audit/{_bandit,_shellcheck,_pip_audit,_format,_runner}.py`
  (moved). `_github.py` becomes a thin re-export.
- CHANGELOG: 0.3.0 deprecation section.
- Tests: minimal shim tests (8 AAA-marked, mirroring the W1
  scitex-security-shim test suite I had built for the on-hold #12).

**Phase 3 — scitex-dev ecosystem reconciliation (reverse of #141).**

- `src/scitex_dev/_ecosystem/_registry.py`: 
  - `scitex-security`: REMOVE `archived=True` (un-archive).
  - `scitex-audit`: ADD `archived=True`.
- Comment block on both entries references ADR-0002.
- Single PR. Same-wave with the scitex-security 0.2.0 publish.

**Phase 4 — scitex-python umbrella (reverse of #322).**

- `src/scitex/__init__.py`:
  `security = _LazyModule("security", external="scitex_audit.github")`
  → `security = _LazyModule("security", external="scitex_security")`
  (back to the original).
- `src/scitex/re_export.py` alias map:
  `"security": "scitex_audit.github"` → `"security": "scitex_security"`.
  (`"audit"` stays — it still has a published 0.2.0; the 0.3.0 shim
  will resolve via the standard scitex-audit PyPI package.)
- `pyproject.toml`:
  - `[security]` extra: `["scitex-audit>=0.2.0"]` → `["scitex-security>=0.2.0"]`.
  - `[audit]` extra: `["scitex-audit==0.2.0"]` → `["scitex-audit>=0.3.0"]`
    (the shim) AND `["scitex-security>=0.2.0"]` (transitively pulled).
  - Main deps: keep `scitex-security==0.2.0`; bump `scitex-audit==0.3.0`.

**Phase 5 — release wave.**

| Step | Repo | Action | Block on |
| --- | --- | --- | --- |
| 5.1 | scitex-dev | Merge this ADR PR (ADR-0001 + ADR-0002 + registry reversal). | Lead sanity-check, then explicit `gh --head --base develop`. |
| 5.2 | scitex-security | Merge the absorption PR (0.2.0). Tag v0.2.0. Wait for PyPI publish. | scitex-audit 0.2.0 on PyPI is not blocking — scitex-security 0.2.0 is self-contained. |
| 5.3 | scitex-audit | Merge the shim PR (0.3.0). Tag v0.3.0. Wait for PyPI publish. | scitex-security 0.2.0 on PyPI (the new shim depends on it). |
| 5.4 | scitex-python | Merge the umbrella reversal PR. | scitex-security 0.2.0 on PyPI. |
| 5.5 | scitex-dev | Close the on-hold scitex-security #12 with a pointer comment. | Phase 5.2 merged. |

### What this ADR does NOT decide

- Whether to also yank `scitex-audit 0.2.0` from PyPI. **Decided
  above: NO** (yanks break installed callers and pile churn on
  external users we don't control). Re-evaluated never; the
  decision is "let the deprecated path exist on PyPI permanently."
- The exact verb-noun shape of the new scitex-security CLI when
  combining audit-runner + GH-alerts. Suggested: `scitex-security
  check` for the multi-tool scan (matches scitex-audit 0.2.0's
  `audit(.)` entry), `scitex-security github check` for GH-alerts.
  Flag for lead.

### History note (provenance — important for future readers)

This is the SECOND ADR in scitex-dev's docs/adr/ even though it
appears as `0002-*`. The numbering is correct: ADR-0001 (the
superseded direction) was drafted, Accepted, and W1-executed on
2026-06-07 morning; the publish + 3 of 4 dependent PRs were merged
before the operator's afternoon direction-reversal call. ADR-0001
exists for the historical record (the absorbing target `scitex-audit
0.2.0` IS still on PyPI as historical artifact); ADR-0002 documents
the reversed direction that all subsequent work follows.

## Consequences

**Positive**
- The unified package name matches the operator's mental model of the
  surface ("security" > "audit" for the broader concept).
- No PyPI yank — clean release history; nobody's installed version
  breaks abruptly.
- The reversal-symlink in scitex-security NEXT means users who ever
  ran scitex-audit 0.2.0 get auto-migrated back to the canonical
  `~/.scitex/security/runtime/` directory.
- The "no per-module `scitex/security/__init__.py` bridge file" call
  from W1 still holds — the umbrella's `_LazyModule + alias_map` is
  the canonical bridge mechanism for every absorbed module (the call
  the lead specifically endorsed). It just retargets to
  `scitex_security` instead of `scitex_audit.github`.

**Negative / cost**
- One extra PyPI release on each side (scitex-audit 0.3.0 shim,
  scitex-security 0.2.0 unified) — bandwidth tax on the index but
  small in absolute terms.
- The release-history of scitex-audit shows `0.1.x (orchestrator) →
  0.2.0 (orchestrator + absorbed GH-alerts) → 0.3.0 (deprecated
  shim of scitex-security)`. The 0.2.0 row is the "wrong-direction
  W1 release that we reversed." Documenting the reversal in
  CHANGELOG explicitly so future archaeology has the answer.
- The scitex-security CLI now grows to cover bandit/shellcheck/
  pip-audit verbs — bigger surface, more rules to satisfy. Mitigated
  by the existing scitex-security 0.1.4 CLI already being canonical
  in shape (the W1 scitex-audit CLI was structured by copying it
  verbatim).
- ~30 minutes of operator/lead time burnt on the direction debate.
  Acceptable.

**Avoided cost (vs. status quo)**
- "Status quo" here would mean keeping the W1-shipped direction
  (security → audit) against the operator's preference, baking in a
  package name he doesn't want as the canonical survivor. That's a
  decision that gets harder to reverse the longer it sits — better
  to flip now before the on-hold shim publishes.

## Notes

- **Provenance.** Operator's afternoon-2026-06-07-JST direction call
  via lead, after questioning the absorption direction post-publish.
  Lead's 2026-06-07 16:30-ish UTC message ("Operator chose 1b — REVERSE
  the direction") is the canonical decision record.
- **Supersedes.** ADR-0001
  (`docs/adr/0001-absorb-scitex-security-into-scitex-audit.md`), Accepted
  same day, W1-executed up through the scitex-audit 0.2.0 PyPI publish.
- **Skill references** (same as ADR-0001):
  `_skills/general/01_ecosystem/03_modules-and-standalone-packages.md`
  (when-to-merge-back), `05_re-export.md` (named re-export bridge),
  `03_interface/02_cli/11_deprecation.md` (hard-error redirect).
- Open follow-ups (post-W1-reverse cleanup queue):
  1. Drop the dangling `origin/docs/adr-absorb-security` branch
     after this PR merges (its content has been resurrected into
     `develop` by this PR).
  2. Write the gh-CLI cwd-detect preventive into
     `_skills/general/04_docs/` or the cross-repo gate doc:
     **always pass explicit `--head <branch> --base <branch>` on
     `gh pr create`; cwd / worktree auto-detection silently targets
     the wrong branch.**
  3. develop ⇄ main reconciliation: ADR-0001 lives on a dangling
     branch (resurrected here); `chore/registry-archive-scitex-security`
     was misfired to main; future scitex-dev PRs all target develop.
  4. The 5 stale umbrella pins (scitex-dev 0.17.6, scitex-io 0.3.1,
     scitex-db 0.1.12, scitex-msword 0.3.2, scitex-dataset 0.4.0)
     stay queued as a SEPARATE coordinated version-reconcile sweep —
     NOT bundled into this wave (operator's own diff-aware-audit
     philosophy: focused PRs only).
  5. The `sync main → release tag` workflow failure on scitex-audit
     after the v0.2.0 tag — investigate after the reverse wave.
