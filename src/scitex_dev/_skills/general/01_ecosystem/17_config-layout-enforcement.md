---
description: |
  [TOPIC] `.scitex/<pkg-short>/` config-layout enforcement (PS-222)
  [DETAILS] The mechanical rule behind 06_dot_scitex_directory's tracked/runtime split: everything directly under a package's local-state root is TRACKED except `runtime/`, the primary config is always `config.yaml` (never a `<pkg-short>.yaml` alias), and a package scope is always a directory (never a bare `.scitex/<pkg>.yaml` file). Covers the three arms, the `runtime/` control arm, ignored-vs-untracked, severity W, `audit.exemptions` opt-out, and why PS-180 is a different tree.
tags: [scitex-general-ecosystem-config-layout-enforcement]
---

# Config-Layout Enforcement — `PS-222 scitex-config-layout`

`01_ecosystem/06_dot_scitex_directory.md` §4a/§4b **describe** the split
between tracked config and gitignored runtime state. This file is the
**mechanical rule** that enforces it, and the invariant states in one line:

> Everything directly under `<pkg-short>/` — at project scope
> (`<repo>/.scitex/<pkg-short>/`) or user scope (`~/.scitex/<pkg-short>/`) —
> is **TRACKED**, except `runtime/`.

`scitex-dev audit-project` grades the tree it can see: the project-scope one.

## 1. The three arms

| # | Fires on | The landmine |
|---|---|---|
| 1 | A **gitignored** entry directly under `<pkg-short>/` whose name is not `runtime` | Config that CI never sees. The audit tool's own config is the worked example (`06_dot_scitex_directory.md` §1, incident 2026-05-11): the whole `.scitex/` tree was gitignored, so a locally-added scitex-io whitelist made PS-103 pass on the maintainer's machine and keep failing in CI, with nothing pointing at the divergence. Generalised: an ignored tracked-side path turns "works for me" into an **unfalsifiable** claim, because the reviewer's checkout does not contain the file that produced the result. |
| 2 | A deprecated primary-config alias — `<pkg-short>.yaml` or `<pkg-short>_config.yaml` | Two plausible config paths where the loader honours one. A reader edits `dev.yaml`, the package reads `config.yaml`, and the edit does nothing: no error, no warning, just an unchanged run. |
| 3 | A bare `<something>.yaml` **file** sitting directly in `.scitex/` | The form `06_dot_scitex_directory.md` §5 already forbids. A single file has nowhere to put `runtime/`, so the tracked/runtime split this convention rests on cannot exist there at all. |

Each offending entry produces its own finding — two breaches in one scope
are two findings at two sites, never one merged report.

## 2. `runtime/` is never flagged — the control arm

Arm 1 skips `runtime/` unconditionally. Being gitignored is precisely what
the convention *requires* of it; flagging it would invert the rule.

This is the rule's **control arm**, and it is pinned by a test
(`test_ps222_stays_silent_for_gitignored_runtime_dir`). The reason it must
exist as its own test: a mutation that made the check flag *everything*
would leave every positive test in the file green. Only the control arm
goes red. A rule with positive tests alone cannot distinguish "correct"
from "flags all input".

## 3. Ignored, not merely untracked

Arm 1 grades **ignored** paths, not untracked ones.

- A file created five minutes ago is *untracked but not ignored* —
  uncommitted work, not a layout breach. Flagging it would make the rule
  fire on every work-in-progress checkout, and a rule that fires on normal
  work gets skipped rather than fixed.
- An **ignored** path cannot become tracked without editing `.gitignore`.
  That is a permanent, deliberate divergence from the convention, and it is
  what the rule is for.

Status comes from `git check-ignore` run in the audited tree, batched
through one `--stdin` call. The auditor never imports the audited package,
so it is safe on broken trees. If git cannot be consulted at all, the check
claims **nothing is ignored** and reports nothing — it does not report a
clean tree it was unable to evaluate.

## 4. Severity — `W`, deliberately

PS-222 ships at **warning**, for every project type.

The precedent is PS-220: promoted to `E` ecosystem-wide in PR #406, which
newly FAILED 44 repos on 1856 findings and was restaged to `W` the next
day. A layout convention landing red across the fleet buys nothing that a
visible warning does not, and costs every repo's green build. Shipping at
`W` also means the first ecosystem-wide measurement happens while the fleet
can still merge.

The severity lives in the rule tuple in `_check_config_layout.py`, **not**
in `_registry._SEVERITY_OVERRIDES`. `_patch` (which applies that table) runs
at the very bottom of `_registry.py`, after co-located rule sets are merged,
so an override added there for a co-located rule is a silent no-op.

## 5. Opting out — `audit.exemptions`, reason mandatory

The only sanctioned hatch. The `# noqa` form was removed ecosystem-wide on
2026-07-23 and is not available here.

```yaml
# <repo>/.scitex/dev/config.yaml
audit:
  exemptions:
    PS-222:
      - path: .scitex/scholar/legacy-cache
        line: 0
        reason: "frozen pre-migration tree, removed in v0.9"
```

- PS-222 findings are per-**path**, not per-line, so every entry pins
  `line: 0`.
- `path` is compared verbatim against the repo-relative POSIX path, so an
  exemption pins **one** site — it cannot drift into covering a directory
  or the whole rule.
- A blank or whitespace-only `reason` is **REJECTED**: the site still
  fires, *and* the rejection is itself reported at `E`. Config errors are
  never staged. A suppression with no stated reason is exactly the
  unexamined silence the rule exists to catch.

## 6. Not to be confused with PS-180

`PS-180` (`_check_runtime_separation.py`) also carries "runtime" in its name
and also concerns a directory called `runtime/` — and it is a **different
tree with a different failure mode**:

| | PS-180 | PS-222 |
|---|---|---|
| Tree | `src/<pkg>/runtime/` — inside the shipped Python package | `.scitex/<pkg-short>/runtime/` — local state on disk |
| Question | What may be imported at module scope? | What does git track? |
| Doc | `02_package/02_project-structure-src.md` | this file + `01_ecosystem/06_dot_scitex_directory.md` |

Neither supersedes the other; both should fire when both are violated.

`PS-145` / `PS-146` / `PS-147` (`_check_local_state.py`) are adjacent in the
same way: they also derive from `06_dot_scitex_directory.md`, but they grade
**source code** (cross-package state reads, pip-install side effects,
shell-completion install shape). PS-222 grades the **directory on disk**.
No functional overlap.

## 7. Checklist

- [ ] Nothing directly under `.scitex/<pkg-short>/` is gitignored except `runtime/`.
- [ ] The primary config is named `config.yaml` — no `<pkg-short>.yaml`, no `<pkg-short>_config.yaml`.
- [ ] Every package scope is a **directory**; no bare `.scitex/<pkg>.yaml` file.
- [ ] Genuinely regenerable per-host state lives under `runtime/`, not beside `config.yaml`.
- [ ] Any `.gitignore` re-include under `.scitex/` uses **file-level** negation (a dir-level exclusion blocks negation — `06_dot_scitex_directory.md` §1).
- [ ] Every `audit.exemptions` PS-222 entry states a real reason.

## 8. Related

- `01_ecosystem/06_dot_scitex_directory.md` — the layout this rule enforces (§4a tracked, §4b runtime, §5 forbidden locations).
- `01_ecosystem/12_local-state-resolution.md` — resolving these paths in code (`path()` / `user_path()` / `runtime_path()`).
- `09_quality/03_verification-doctrine.md` — why the control arm in §2 is not optional.

<!-- EOF -->
