# -*- coding: utf-8 -*-
"""PS-222 — `.scitex/<pkg-short>/` config-layout convention.

The convention (canonical text: `_skills/general/01_ecosystem/
06_dot_scitex_directory.md` §4a/§4b/§5, and §12 for this rule) splits every
package's local-state root into exactly two halves:

  * **tracked** — everything directly under `<pkg-short>/`: `config.yaml`
    (the canonical primary config), an optional `config/` split directory,
    `bin/`, `shared/`, and friends. These are declarative inputs the team
    commits and reviews.
  * **runtime** — `<pkg-short>/runtime/`, and ONLY that. Regenerable,
    per-host, sometimes sensitive; the one gitignored subdirectory.

Hence the invariant this rule enforces:

    Everything directly under `<pkg-short>/` EXCEPT `runtime/` is TRACKED.

Anti-landmine this prevents
---------------------------

Two distinct silent failures, one per arm.

1. **A gitignored non-`runtime/` entry** means config that CI never sees.
   The audit-tool's own `.scitex/dev/config.yaml` is the worked example
   (§1): when the whole `.scitex/` tree was gitignored, a locally-added
   whitelist entry made the audit pass on the maintainer's machine and keep
   failing in CI, with nothing to point at the divergence (incident
   2026-05-11, scitex-io PS-103). Generalised: any tracked-side path that
   quietly falls out of git turns "works for me" into an unfalsifiable
   claim, because the reviewer's checkout does not contain the file that
   produced the result.

2. **A deprecated `<pkg-short>.yaml` alias** means two plausible config
   paths where the loader honours one. A reader edits `dev.yaml`, the
   package reads `config.yaml`, and the edit does nothing — no error, no
   warning, just an unchanged run. §5 already forbids the bare-file form
   (`./.scitex/<pkg>.yaml`) for the same reason: the scope is always a
   DIRECTORY, never a single file.

Decision rule the auditor enforces
----------------------------------

For each directory `D` directly under `<repo>/.scitex/`:

  1. Any entry directly under `D` whose name is NOT `runtime` and which git
     reports as IGNORED → PS-222.
  2. A deprecated primary-config alias inside `D` — `<D-name>.yaml`,
     `<D-name>.yml`, or `<D-name>_config.yaml` → PS-222. The canonical name
     is always `config.yaml`.

Plus, at the `.scitex/` root itself:

  3. A bare FILE named `<something>.yaml` / `.yml` sitting directly in
     `.scitex/` (rather than a `<pkg-short>/` directory) → PS-222, per §5.

`runtime/` is never flagged by arm 1 — being gitignored is precisely what
the convention requires of it. That is the rule's control arm, and
`test__check_config_layout.py` pins it: a mutation that makes the check
flag EVERYTHING must turn that test red.

Tracked vs merely-uncommitted
-----------------------------

Arm 1 flags IGNORED paths, not merely untracked ones. A file the developer
created five minutes ago is untracked but not ignored — it is uncommitted
work, not a layout violation, and flagging it would make the rule fire on
every work-in-progress checkout. An IGNORED path, by contrast, can never
become tracked without editing `.gitignore`, so it is a genuine, permanent
divergence from the convention. Ignore status is read via
`git -C <repo> check-ignore`, batched through one `--stdin` invocation.

The auditor never imports the audited package — it reads the filesystem and
shells `git` in the audited tree, so it is safe to run on broken trees.

Prior art — adjacent, NOT superseded
------------------------------------

* **PS-180** (`_check_runtime_separation.py`) governs `src/<pkg>/runtime/`
  — a directory INSIDE the shipped Python package, about what may be
  imported at module scope. This rule governs `.scitex/<pkg-short>/runtime/`
  — local state on disk, about what git tracks. The names collide; the
  trees, the failure modes and the remedies do not. Neither supersedes the
  other and both should fire when both are violated.
* **PS-145 / PS-146 / PS-147** (`_check_local_state.py`) also derive from
  `06_dot_scitex_directory.md`, but grade SOURCE CODE (cross-package reads,
  pip-install side effects, completion install shape). PS-222 grades the
  DIRECTORY ON DISK. Adjacent, non-overlapping.

Severity — W, and deliberately so
---------------------------------

Flat `severity = "W"`. The precedent is documented at length in
`_check_no_print.py:70-104`: PR #406 promoted PS-220 to `E`
ecosystem-wide, 44 repos newly FAILED on 1856 findings, and the operator
restaged it to `W` the next day. A layout rule that lands red across the
fleet buys nothing that a visible warning does not, and costs every repo's
green build. Shipping at `W` also means the first ecosystem-wide
measurement happens with the fleet still able to merge.

The severity lives in the rule tuple below, NOT in
`_registry._SEVERITY_OVERRIDES` — `_patch` is applied at the BOTTOM of
`_registry.py`, after co-located rule sets are merged, and an override
added for a co-located rule before that point is silently ignored
(`_registry.py:1173-1184`).

Exemptions
----------

The only sanctioned opt-out is `audit.exemptions` in
`.scitex/dev/config.yaml`, keyed by rule code, with a MANDATORY written
`reason`::

    audit:
      exemptions:
        PS-222:
          - path: .scitex/scholar/runtime-legacy
            line: 0
            reason: "frozen pre-migration tree, removed in v0.9"

`line: 0` — PS-222 findings are per-PATH, not per-line, so every exemption
pins line 0. A blank or whitespace-only reason is REJECTED: the site still
fires, AND the rejection is itself reported at `E` (config errors are never
staged — same contract as `_check_no_print.py:105-113`). The `# noqa`
hatch was removed ecosystem-wide on 2026-07-23 and is not available here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# The registered severity of the rule tuple below. `_emit` only sets a
# per-finding override when the effective severity DIFFERS from this, so the
# rule's registered severity stays the default story a reader gets.
_DEFAULT_SEVERITY = "W"

# Config errors (a rejected `audit.exemptions` entry) are reported at E
# regardless of the rule's own severity: a malformed override is not
# migration debt, and must never read as a quiet no-op the author believes
# worked.
_CONFIG_ERROR_SEVERITY = "E"

# PS-222 findings are per-PATH; there is no meaningful line number, so both
# the emitted site and any exemption entry pin line 0.
_NO_LINE = 0

# The one sanctioned gitignored subdirectory under `<pkg-short>/`.
_RUNTIME = "runtime"

# The canonical primary-config filename. Anything else that looks like a
# primary config is a deprecated alias.
_CANONICAL = "config.yaml"

_FIX_TRACKED = (
    "Fix: track it (`git add` it and drop the ignore rule), or — if it is "
    "genuinely regenerable per-host state — MOVE it under "
    "`<pkg-short>/runtime/`, which is the one subdirectory the convention "
    "gitignores. Use file-level negation under `.scitex/` so the re-include "
    "actually applies (a dir-level exclusion blocks negation): "
    "`.scitex/*` / `!.scitex/<pkg-short>/` / ... — see "
    "`_skills/general/01_ecosystem/06_dot_scitex_directory.md` §1."
)

_FIX_ALIAS = (
    "Fix: rename it to `config.yaml`. The primary config filename is "
    "canonical across the ecosystem — never `<pkg>.yaml`, never "
    "`<pkg>_config.yaml` — so tooling, docs and the precedence chain "
    "(`03_interface/02_cli/12_config-and-env.md` §6b) all agree on one "
    "path. Two plausible paths where the loader honours one means an edit "
    "to the wrong file silently does nothing. See "
    "`_skills/general/01_ecosystem/06_dot_scitex_directory.md` §4a."
)

_FIX_BARE_FILE = (
    "Fix: move it to `.scitex/<pkg-short>/config.yaml`. A package's scope "
    "is always a DIRECTORY, never a single file at `.scitex/<pkg>.yaml` — "
    "the bare-file form has nowhere to put `runtime/`, so the tracked / "
    "runtime split the convention rests on cannot exist. See "
    "`_skills/general/01_ecosystem/06_dot_scitex_directory.md` §5."
)


def _ignored_paths(repo: Path, candidates: list[Path]) -> set[Path]:
    """Subset of `candidates` that git reports as IGNORED in `repo`.

    One batched `git check-ignore --stdin` call. Paths are fed relative to
    the repo root and the matching results are mapped back to the absolute
    inputs. A git failure (not a repo, git absent, ...) yields the EMPTY set
    — i.e. nothing is claimed to be ignored, so the check reports nothing
    rather than reporting a clean tree it could not evaluate.
    """
    if not candidates:
        return set()
    rels: list[str] = []
    by_rel: dict[str, Path] = {}
    for cand in candidates:
        try:
            rel = cand.relative_to(repo).as_posix()
        except ValueError:  # pragma: no cover - candidates come from `repo`
            continue
        rels.append(rel)
        by_rel[rel] = cand
    if not rels:
        return set()
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "check-ignore", "--stdin"],
            input="\n".join(rels) + "\n",
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    # check-ignore exits 0 (some ignored), 1 (none ignored), 128 (error).
    if proc.returncode not in (0, 1):
        return set()
    out: set[Path] = set()
    for line in proc.stdout.splitlines():
        hit = by_rel.get(line.strip())
        if hit is not None:
            out.add(hit)
    return out


def _is_deprecated_alias(name: str, pkg_short: str) -> bool:
    """True iff `name` is a deprecated primary-config alias for `pkg_short`.

    `config.yaml` is canonical and never an alias. `config.yml` is not
    flagged here — it is a suffix quibble, not a second plausible NAME, and
    the alias arm is about the "two files, one honoured" failure mode.
    """
    if name == _CANONICAL:
        return False
    lowered = name.lower()
    short = pkg_short.lower()
    return lowered in {
        f"{short}.yaml",
        f"{short}.yml",
        f"{short}_config.yaml",
        f"{short}_config.yml",
    }


def _emit(out: list, violation_cls, severity: str, where: str, detail: str):
    """Append a PS-222 violation, carrying a per-finding severity override.

    `Violation.severity_override` is the auditor's established per-finding
    severity mechanism (`_violation.py:19-25`). It is set only when it would
    change something — i.e. when `severity` differs from the rule tuple's
    REGISTERED severity.
    """
    v = violation_cls("PS-222", where, detail)
    if severity != _DEFAULT_SEVERITY:
        try:
            v.severity_override = severity
        except (AttributeError, TypeError):  # pragma: no cover - stub classes
            pass
    out.append(v)
    return v


def _report_config_errors(repo: Path, config, violation_cls, out: list) -> None:
    """Surface rejected `audit.exemptions` entries for PS-222, at `E`.

    A rejected exemption exempts NOTHING — the site still fires. Reporting
    the rejection separately is what keeps a reasonless exemption from
    reading as a quiet pass the author believes worked.
    """
    for notice in tuple(getattr(config, "exemption_errors", ()) or ()):
        if not notice.startswith("PS-222"):
            continue
        _emit(
            out,
            violation_cls,
            _CONFIG_ERROR_SEVERITY,
            str(repo / ".scitex/dev/config.yaml"),
            (
                f"Invalid `audit.exemptions` entry — {notice}. The entry "
                f"does NOT exempt anything; an exemption must state WHY "
                f"the site is exempt."
            ),
        )


def check_ps222_config_layout(
    repo: Path,
    violation_cls: type,
    out: list,
    *,
    config=None,
) -> None:
    """Append PS-222 violations for `.scitex/<pkg-short>/` layout breaches.

    Parameters
    ----------
    repo : Path
        Repository root (the dir containing `.scitex/`).
    violation_cls : type
        The auditor's `Violation` dataclass `(rule, where, detail)`.
    out : list
        Violations are appended in place (project-auditor convention).
    config : ProjectConfig, optional
        Pre-loaded project config. When omitted it is loaded from `repo` so
        the check honours `audit.exemptions` on its own; passing it in lets
        a caller that already loaded the config avoid a second read.
    """
    scitex_dir = repo / ".scitex"
    if not scitex_dir.is_dir():
        return

    if config is None:
        try:
            from .._config import load_config

            config = load_config(repo)
        except Exception:  # pragma: no cover - config is best-effort here
            config = None

    if config is not None:
        _report_config_errors(repo, config, violation_cls, out)

    exemption_for = getattr(config, "exemption_for", None)

    def _exempt(path: Path) -> bool:
        if exemption_for is None:
            return False
        try:
            rel = path.relative_to(repo).as_posix()
        except ValueError:  # pragma: no cover
            return False
        return bool(exemption_for("PS-222", rel, _NO_LINE))

    try:
        top = sorted(scitex_dir.iterdir())
    except OSError:
        return

    # Arm 3 — a bare `<something>.yaml` FILE directly in `.scitex/`.
    for entry in top:
        if entry.is_file() and entry.suffix.lower() in (".yaml", ".yml"):
            if _exempt(entry):
                continue
            _emit(
                out,
                violation_cls,
                _DEFAULT_SEVERITY,
                str(entry),
                (
                    f"bare config FILE `{entry.name}` directly under "
                    f"`.scitex/` — a package's scope must be a DIRECTORY "
                    f"`.scitex/<pkg-short>/`. {_FIX_BARE_FILE}"
                ),
            )

    pkg_dirs = [d for d in top if d.is_dir()]
    if not pkg_dirs:
        return

    # Arms 1 + 2, per package-scope directory.
    candidates: list[Path] = []
    for pkg_dir in pkg_dirs:
        try:
            children = sorted(pkg_dir.iterdir())
        except OSError:
            continue
        for child in children:
            if child.name != _RUNTIME:
                candidates.append(child)

    ignored = _ignored_paths(repo, candidates)

    for pkg_dir in pkg_dirs:
        pkg_short = pkg_dir.name
        try:
            children = sorted(pkg_dir.iterdir())
        except OSError:
            continue
        for child in children:
            # `runtime/` is the ONE gitignored subdirectory the convention
            # requires. It is exempt from the tracked-ness arm BY DESIGN —
            # this branch is the rule's control arm.
            if child.name == _RUNTIME:
                continue
            if _exempt(child):
                continue
            if child in ignored:
                kind = "directory" if child.is_dir() else "file"
                _emit(
                    out,
                    violation_cls,
                    _DEFAULT_SEVERITY,
                    str(child),
                    (
                        f"gitignored {kind} `{child.name}` directly under "
                        f"`.scitex/{pkg_short}/`. Everything directly under "
                        f"`<pkg-short>/` except `runtime/` must be TRACKED — "
                        f"an ignored entry here is config CI never sees, so "
                        f'"works on my machine" becomes unfalsifiable. '
                        f"{_FIX_TRACKED}"
                    ),
                )
                continue
            if child.is_file() and _is_deprecated_alias(child.name, pkg_short):
                _emit(
                    out,
                    violation_cls,
                    _DEFAULT_SEVERITY,
                    str(child),
                    (
                        f"deprecated primary-config alias "
                        f"`.scitex/{pkg_short}/{child.name}` — the canonical "
                        f"name is `{_CANONICAL}`. {_FIX_ALIAS}"
                    ),
                )


# Rule definition, CO-LOCATED with its check (same pattern as PS-221's
# `ALL_CLOSURE_RULES` / PS-220's `PRINT_FORBIDDEN_RULES`). `_registry.py`
# merges `CONFIG_LAYOUT_RULES` on identical terms, at the BOTTOM of the
# module — the severity below is the one that ships, because
# `_SEVERITY_OVERRIDES` cannot reach a co-located rule (see
# `_registry.py:1173-1184`).
#
# Severity W (warning): a layout convention landing red across the fleet
# buys nothing a visible warning does not, and costs every repo's green
# build — the PS-220 lesson (promoted to E in PR #406, 44 repos newly
# failing on 1856 findings, restaged to W the next day).
#
# (code, section, message, severity, slug)
CONFIG_LAYOUT_RULES: list[tuple[str, str, str, str, str]] = [
    (
        "PS-222",
        "§4a",
        (
            "`.scitex/<pkg-short>/` config-layout breach: everything directly "
            "under a package's local-state root must be TRACKED except "
            "`runtime/`, which is the one gitignored subdirectory. Flags (a) a "
            "gitignored non-`runtime/` entry — config CI never sees, which "
            "makes a local pass unfalsifiable; (b) a deprecated primary-config "
            "alias `<pkg-short>.yaml` / `<pkg-short>_config.yaml` — the "
            "canonical name is `config.yaml`, and two plausible paths where "
            "the loader honours one means an edit that silently does nothing; "
            "(c) a bare `.scitex/<pkg>.yaml` FILE — the scope is always a "
            "DIRECTORY, since a bare file has nowhere to put `runtime/`. Fix: "
            "track it, or move genuinely regenerable state under `runtime/`; "
            "rename an alias to `config.yaml`. See "
            "`_skills/general/01_ecosystem/06_dot_scitex_directory.md` "
            "§4a/§4b/§5/§12."
        ),
        "W",
        "scitex-config-layout",
    ),
]


# EOF
