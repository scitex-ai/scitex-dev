# Plugin audit — 2026-06-15

Audit of every scitex leaf that registers a `scitex_dev.linter.plugins`
entry-point, looking for the same antipattern trio that hid figrecipe's
figure-style checkers for months (lead a2a `b27d8646`; fixes shipped in
scitex-dev #190 + figrecipe #170).

## Methodology

1. Grepped each candidate leaf's `pyproject.toml` for
   `[project.entry-points."scitex_dev.linter.plugins"]`.
2. Read the referenced module verbatim.
3. Looked for the three antipatterns:
   - **(1) Factory-returns-None on ImportError** — `get_plugin()` (or a
     helper it calls) wraps a build-time `scitex_dev.linter.*` import in
     a `try / except ImportError: return None` (or returns an empty dict
     in a way that silently drops checkers).
   - **(2) Build-time `scitex_dev` import at module load** — top-of-file
     `from scitex_dev.linter... import ...`. This is the circular-import
     trigger because `load_plugins` runs DURING `scitex_dev.linter.checker`
     module import (figrecipe canary).
   - **(3) Silent except-pass on the load → register → invoke path** —
     any `except Exception: pass` (or equivalent) inside the leaf's
     plugin module that would mask a failure to the linter.

Leaf candidates discovered (gitignored worktree copies / dotscitex
clones de-duplicated):

| Leaf                       | Plugin module                                                                       |
| -------------------------- | ----------------------------------------------------------------------------------- |
| scitex-io                  | `scitex_io/_linter_plugin.py`                                                       |
| scitex-stats               | `scitex_stats/_linter_plugin.py`                                                    |
| scitex-clew                | `scitex_clew/_linter_plugin.py`                                                     |
| scitex-audio               | `scitex_audio/_linter_plugin.py`                                                    |
| scitex-agent-container     | `scitex_agent_container/_linter_plugin.py`                                          |
| scitex-notification        | `scitex_notification/_linter_plugin.py`                                             |

Two extra grep hits (`scitex-code`, `scitex-python`) turned out to be
*comments* describing the deprecated entry-point — both leaves have
already dropped the registration (Phase B). Skipped.

Worktree copies (`*.worktrees/...`, `*-dotscitex`, `*-p1fix`,
`*-c2-observe-tasks`, `*-wt-skills`) were not separately audited — they
mirror the canonical leaf path.

## Per-leaf findings

### scitex-io

- pyproject entry-point: `io = "scitex_io._linter_plugin:get_plugin"`
- Module path: `~/proj/scitex-io/src/scitex_io/_linter_plugin.py`
- Antipattern (1) factory-returns-None: **NO**. `get_plugin()` never
  returns `None`; it returns the full dict unconditionally.
- Antipattern (2) build-time `scitex_dev` import: **NO**. All
  `scitex_dev.linter.*` imports are *inside* function bodies (line 196
  `_emit` lazy import of `Rule`; line 223 `_emit` lazy import of `Issue`;
  line 237 inside `get_plugin`). Nothing at module top.
- Antipattern (3) silent except-pass on load path: **NO** load-path mask.
  There is a bare `except Exception: return <fallback set>` at line 52
  inside `_builtin_extensions()`, but that only falls back to a
  hardcoded extension set for IO014's "known extensions" lookup — it
  does **not** suppress plugin loading or rule emission. Acceptable.
- Verdict: **CLEAN**.
- Suggested fix: none. (For belt-and-braces, `_builtin_extensions()`'s
  bare `except Exception` could be narrowed to `ImportError`, but this
  is cosmetic — it's not on the plugin-load path.)

### scitex-stats

- pyproject entry-point: `stats = "scitex_stats._linter_plugin:get_plugin"`
- Module path: `~/proj/scitex-stats/src/scitex_stats/_linter_plugin.py`
- Antipattern (1) factory-returns-None: **NO**. Always returns the full dict.
- Antipattern (2) build-time `scitex_dev` import: **NO**. Single
  `scitex_dev.linter._rules._base.Rule` import is inside `get_plugin()`
  (line 10), not at module top.
- Antipattern (3) silent except-pass: **NO**. No `try/except` anywhere
  in the file.
- Verdict: **CLEAN**.
- Suggested fix: none.

### scitex-clew

- pyproject entry-point: `clew = "scitex_clew._linter_plugin:get_plugin"`
- Module path: `~/proj/scitex-clew/src/scitex_clew/_linter_plugin.py`
- Antipattern (1): **NO**. Returns a placeholder dict with empty
  rules/call_rules/axes_hints/checkers — by design, intentional no-op.
- Antipattern (2): **NO**. No `scitex_dev` import at all.
- Antipattern (3): **NO**. No `try/except`.
- Verdict: **CLEAN** (intentional no-op placeholder; safe).
- Suggested fix: none. (When CW rules are added, mirror scitex-io's
  lazy-import discipline.)

### scitex-audio

- pyproject entry-point: `scitex-audio = "scitex_audio._linter_plugin:get_plugin"`
- Module path: `~/proj/scitex-audio/src/scitex_audio/_linter_plugin.py`
- Antipattern (1): **NO**. Returns the empty placeholder dict.
- Antipattern (2): **NO**. No `scitex_dev` import.
- Antipattern (3): **NO**.
- Verdict: **CLEAN** (intentional no-op placeholder; safe).
- Suggested fix: none. (Mirror scitex-io discipline when rules land.)

### scitex-agent-container

- pyproject entry-point: `scitex-agent-container = "scitex_agent_container._linter_plugin:get_plugin"`
- Module path: `~/proj/scitex-agent-container/src/scitex_agent_container/_linter_plugin.py`
- Antipattern (1) factory-returns-None: **NO**. `get_plugin()` always
  returns the dict with both `_SacCardChecker` and `_SacMethodChecker`.
- Antipattern (2) build-time `scitex_dev` import: **NO**. The
  `scitex_dev.linter._rules._base.Rule` import is inside `get_plugin()`
  (line 36); `_get_rule` lazy-imports `_lookup` (line 101); `_make_issue`
  lazy-imports `Issue, _is_allowed_by_comment` (line 114). All are inside
  function bodies — no top-of-file `scitex_dev` import.
- Antipattern (3): **NO** silent except-pass anywhere.
- Verdict: **CLEAN**.
- Suggested fix: none. (Good reference model — same discipline as
  scitex-io.)

### scitex-notification

- pyproject entry-point: `scitex_notification = "scitex_notification._linter_plugin:get_plugin"`
- Module path: `~/proj/scitex-notification/src/scitex_notification/_linter_plugin.py`
- Antipattern (1): **NO**. Returns the empty placeholder dict.
- Antipattern (2): **NO**. No `scitex_dev` import.
- Antipattern (3): **NO**.
- Verdict: **CLEAN** (intentional no-op placeholder; safe).
- Suggested fix: none.

## Summary

| Leaf                   | Verdict | Action |
| ---------------------- | ------- | ------ |
| scitex-io              | CLEAN   | none   |
| scitex-stats           | CLEAN   | none   |
| scitex-clew            | CLEAN   | none (placeholder) |
| scitex-audio           | CLEAN   | none (placeholder) |
| scitex-agent-container | CLEAN   | none   |
| scitex-notification    | CLEAN   | none (placeholder) |

**6 leaves audited. 6 CLEAN. 0 VULNERABLE. 0 DEAD.**

The figrecipe pattern (top-level `try: from scitex_dev.linter.checker
import Issue, _is_allowed_by_comment / except ImportError: return None`
inside a checker-builder helper — confirmed at
`figrecipe/src/figrecipe/_quality/_linter_plugin.py:27-30`) does **not**
appear in any other live leaf.

Common safe patterns the audited leaves share:

1. All `scitex_dev.linter.*` imports live **inside** function bodies
   (`get_plugin`, `_emit`, `_get_rule`, `_make_issue`, the
   `_make_style_kwarg_checker`-style closures). Module load never
   touches `scitex_dev`.
2. Plugins with real checkers (scitex-io, scitex-agent-container) do
   NOT wrap the lazy import in a `try/except` — an import failure would
   raise loudly to `load_plugins`, which (post scitex-dev #190) now
   re-raises rather than swallowing.
3. Empty-placeholder leaves (scitex-clew, scitex-audio,
   scitex-notification) return a fully-shaped dict — never `None` —
   so the loader's shape check is satisfied without exercising any
   `scitex_dev` import path.

## Notes / caveats

- The audit used the canonical `~/proj/<leaf>/` path for each leaf, not
  worktree copies. If a worktree of any of these leaves has diverged,
  those copies were not separately checked.
- `scitex-code` and `scitex-python` `pyproject.toml` hits were
  doc-comment hits — entry-points have been removed (Phase B). Not
  audited as live leaves.
- `/uvwork/venv-agent/bin/python` was not exercised; this is a
  text-only audit and no plugin was imported. (The broken `scitex_dev`
  install in that venv would have been a problem for any dynamic
  check.)

## Recommendation to lead

No per-leaf fix work is required. The fail-loud changes shipped today
in scitex-dev #190 are sufficient — if any of these leaves regresses
into the antipattern later, the new loader behavior will surface it
immediately rather than silently dropping checkers.

The two well-disciplined non-trivial leaves (scitex-io,
scitex-agent-container) are good reference models for any future leaf
adding linter rules. Worth pinning their lazy-import pattern in a short
note in `docs/` so the next plugin author doesn't reinvent the
figrecipe foot-gun.
