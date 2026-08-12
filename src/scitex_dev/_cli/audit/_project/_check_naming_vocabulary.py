# -*- coding: utf-8 -*-
"""PS-230 — retired role vocabulary in package PROSE.

Operator ruling, 2026-08-11 (Telegram):

    「文章が古いっていう問題は、ドックストリングにもスキルにもマークダウン
      ファイルにも言えることで、これかなり困るんですよね。なので見つけたら
      その場で直すっていうのがいいような気がするんですけど」
    — stale prose is a problem in docstrings, in skills and in markdown
      files alike, and it is a real nuisance; the remedy is to fix it the
      moment you find it.

Those three surfaces — **docstrings, skills, markdown** — are exactly this
rule's scope. Fixing-on-sight only works if the stale word is FOUND, and a
convention nobody is reminded of is forgotten at the moment it matters.
``_skills/scitex-dev/25_naming-conventions.md`` says so itself:

    The prose pairs (primary/replica, controller/worker, node/origin) are
    convention until an auditor rule exists — adding one is fair game.

Job NAMES and KINDS were already mechanical (PS-226..PS-229). This closes
the other half: the words.

The table it enforces
---------------------

======================  ====================  =========================
Domain                  Use                   Retired here
======================  ====================  =========================
Credentials             primary / replica     master, slave,
                                              canonical/copy, source/dest
Roles (agents)          controller / worker   master, slave, follower
DB replication          node / origin         master
======================  ====================  =========================

``master`` is the one word that spans all three domains, so the finding
names all three replacements and lets the author pick; the other terms map
to exactly one.

Why ``lead`` is NOT flagged
---------------------------
The naming table retires ``lead/follower`` but records that "``lead``
survives only as the existing agent's name" — and the bare English verb
("leads to", "leading edge") is everywhere. Flagging ``lead`` would fire
overwhelmingly on prose that has nothing to do with roles. Only
``follower``, which has no such second life, is flagged; that is enough to
catch the pair, because the pair is what drifts.

Likewise ``canonical/copy`` and ``source/dest`` are matched ONLY as the
literal slashed pairs. Bare ``canonical``, ``copy`` and ``source`` are
ordinary English and ordinary code vocabulary; flagging them would produce
pure noise.

KNOWN LIMITATION — the DB-replication row is NOT enforced
---------------------------------------------------------
The naming table retires ``primary/replica`` for DB replication
(``scitex_dev.store`` is multi-writer, so the model is ``node/origin``) —
while making those exact words CORRECT for credentials. One word, two
domains, opposite verdicts.

A line-level matcher cannot tell which domain a sentence belongs to, and
the cost of guessing is asymmetric: banning bare ``replica`` would fire on
every correct credential document in the fleet, which is the noise that
gets a rule switched off. So this check does NOT flag ``primary`` or
``replica`` anywhere, and the DB-domain misuse is caught by REVIEW, not
mechanically — ``store/_merge.py``'s stale "a replica that saw the elements
in a different order" was found by reading, not by this rule.

Stated plainly so the gap is known rather than assumed closed. Enforcing it
needs a path-scoped rule (``src/*/store/**`` only), which is a separate,
narrower change. ``test__check_naming_vocabulary.py`` pins the current
behaviour so nobody "fixes" it by widening the term list.

What is SPARED — and why each exemption exists
----------------------------------------------
Every allowlist entry below is a REAL site measured in this repo on
2026-08-11, not a hypothetical. A rule that fires on these is a rule that
gets suppressed wholesale, which is the same as never having added it.

1. **``ControlMaster`` / SSH multiplexing.** OpenSSH's option is spelled
   ``ControlMaster``; ``_hpc_ssh.py``, ``ci/runner/config.py`` and
   ``_spartan_conn_monitor.py`` all discuss "one reused master per host".
   A third-party API name is not ours to rename.
2. **git's ``master`` branch.** ``PROTECTED_BRANCHES = {"develop", "main",
   "master"}`` and every "excludes develop/main/master" docstring. The ref
   is named by git, not by us.
3. **On-disk paths** — ``docs/MASTER/skills/`` is the legacy skills layout
   this package still READS. A path is a contract.
4. **Published contract tokens** — ``--master``,
   ``--install-master-unit``, ``master_host``. A CLI flag, an env var, a
   JSON field or an on-disk key is a MIGRATION (alias, then remove), never
   a prose edit. Renaming the word around a flag that still spells
   ``--master`` makes the documentation LIE, which is strictly worse than
   an out-of-date word.
5. **Lines that are ABOUT the convention or record history** — the naming
   skill's own "banned synonyms" column, a dated incident report, a
   "used to say MASTER" migration note. Prose must be able to name what it
   retired, or the decision cannot be written down at all.

Beyond the allowlist, a site opts out per-line with a trailing
``naming-ok`` marker, or per-site via ``audit.exemptions`` with a
mandatory reason (the PS-220 / PS-222 / PS-223 contract).

Severity — W, deliberately, and measured
----------------------------------------
Flat ``severity = "W"``.

The precedent is explicit and expensive: PS-220 was promoted to ``E``
ecosystem-wide in PR #406, 44 repos newly FAILED on 1856 findings, and the
operator restaged it to ``W`` the next day. PS-227 ships at ``W`` for the
same reason — it flags 34 of 34 declared jobs.

This rule's own exposure is asymmetric in exactly the way that matters:
scitex-dev is swept clean by the PR that introduces it, but the auditor
runs against EVERY SciTeX package, and none of the others has been swept.
Landing at ``E`` would therefore turn sibling repos red for prose while
they are green on code — a build failure that no reviewer can act on
without a docs pass they did not ask for. A visible warning buys the same
correction at none of that cost.

**Promote to ``E`` when** a fleet-wide sweep lands and the corpus measures
zero — by editing the tuple below, NOT ``_registry._SEVERITY_OVERRIDES``,
which is a silent no-op for a co-located rule (see the note beside
``_registry._patch``).
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

# Non-shippable subtrees inside `src/` (an in-package copy of a dev-only
# area). Mirrors PS-220 / PS-223.
_EXCLUDED_PARTS = frozenset({"tests", "scripts", "examples", "docs"})

_DEFAULT_SEVERITY = "W"
_CONFIG_ERROR_SEVERITY = "E"

#: Basenames whose whole job is to DEFINE the vocabulary, and which must
#: therefore be able to NAME the words they retire. The naming skill prints
#: its own "banned synonyms" column; this module's docstring and term table
#: spell out every banned word by construction. Measured 2026-08-11: without
#: the second entry the rule reports 9 findings against ITSELF — a rule that
#: cannot state its own subject without failing is one nobody keeps.
_ALLOWED_FILENAMES = frozenset(
    {
        "25_naming-conventions.md",
        "_check_naming_vocabulary.py",
    }
)

#: Trailing inline opt-out, e.g. ``# ... naming-ok: OpenSSH option name``.
_INLINE_OK = re.compile(r"naming-ok", re.IGNORECASE)

#: The retired terms, each mapped to its replacement guidance.
#: ``(compiled pattern, canonical term, replacement advice)``
_BANNED: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"\bmasters?\b", re.IGNORECASE),
        "master",
        "`primary` (credentials), `controller` (agent/process roles) or "
        "`node` (DB replication in `scitex_dev.store`) — pick the domain",
    ),
    (
        re.compile(r"\bslaves?\b", re.IGNORECASE),
        "slave",
        "`replica` (credentials) or `worker` (agent/process roles)",
    ),
    (
        re.compile(r"\bfollowers?\b", re.IGNORECASE),
        "follower",
        "`worker` (the `lead/follower` pair is retired; `lead` survives "
        "only as the existing agent's name)",
    ),
    (
        re.compile(r"canonical\s*/\s*copy", re.IGNORECASE),
        "canonical/copy",
        "`primary / replica`",
    ),
    (
        re.compile(r"source\s*/\s*dest(ination)?\b", re.IGNORECASE),
        "source/dest",
        "`primary / replica`",
    ),
]

#: Contexts that make a match legitimate. Each carries the REASON it exists,
#: which is printed nowhere but documents the table for the next reader.
#: Matched against the LINE (lowercased) the term appears on.
_ALLOW_CONTEXT: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"control[\s_-]?master|controlpath|controlpersist|multiplex"),
        "OpenSSH ControlMaster / SSH multiplexing — third-party API name",
    ),
    (
        re.compile(
            r"\bgit\b|\bbranch|\borigin/|\bcheckout\b|\brelease/|\brefs?/"
            r"|main\s*/\s*master|master\s*/\s*develop|develop\s*/\s*main"
            r"|main.{0,12}master|master.{0,12}develop|protected"
        ),
        "git branch name — the ref is named by git, not by us",
    ),
    (
        re.compile(r"master/|/master|docs/master|master\.(py|md|txt)"),
        "on-disk path (e.g. the legacy docs/MASTER/skills/ layout)",
    ),
    (
        re.compile(r"--[a-z0-9-]*master|master[_-](host|bearer|unit|token)"),
        "published contract token (CLI flag / JSON field / on-disk key)",
    ),
    (
        re.compile(
            r"\bbanned\b|\bretired\b|\brenamed?\b|naming convention"
            r"|used to (say|be)|\bformerly\b|\bdeprecated\b|\bincident\b"
            r"|\bhistoric|\bwas called\b|\bno longer\b|\bsynonym"
        ),
        "the line is ABOUT the convention, or records history",
    ),
]

_FIX_HINT = (
    "The fleet fixes one word per domain — credentials `primary/replica`, "
    "roles `controller/worker`, DB replication `node/origin` (operator "
    "decision 2026-08-11, `_skills/scitex-dev/25_naming-conventions.md`). "
    "If this occurrence is a PUBLISHED CONTRACT — a CLI flag, an "
    "entry-point group, an env var, a JSON field or an on-disk key — do NOT "
    "rewrite the prose around it: that makes the document lie about the "
    "bytes. Alias the contract first, remove the old spelling later, and "
    "mark this line `naming-ok` with the reason in the meantime."
)


def _prose_files(repo: Path) -> list[Path]:
    """Shippable `.py` and `.md` files under `src/` (best-effort).

    The exclusion is matched against the path RELATIVE TO `src/`, so a
    checkout living under a directory named `docs`/`tests` does not
    silently disable the rule (the PS-223 lesson).
    """
    src = repo / "src"
    if not src.is_dir():
        return []
    out: list[Path] = []
    for pattern in ("*.py", "*.md"):
        for p in src.rglob(pattern):
            if not p.is_file():
                continue
            try:
                rel_parts = set(p.relative_to(src).parts)
            except ValueError:  # pragma: no cover - rglob results are under src
                continue
            if "__pycache__" in rel_parts or rel_parts & _EXCLUDED_PARTS:
                continue
            if p.name in _ALLOWED_FILENAMES:
                continue
            out.append(p)
    return sorted(out)


def _prose_lines_markdown(text: str) -> dict[int, str]:
    """Every line of a markdown file — all of it is prose.

    Fenced code blocks are deliberately INCLUDED: a shell snippet showing
    `--master` is caught by the contract-token allowlist, while a code
    comment carrying a retired role name is exactly what this rule is for.
    """
    return {i: line for i, line in enumerate(text.splitlines(), start=1)}


def _prose_lines_python(text: str) -> dict[int, str]:
    """Line numbers -> source line, for DOCSTRINGS and COMMENTS only.

    Code is excluded by construction. An identifier, a string literal or a
    dict key may be a live contract (`master_host`, `PROTECTED_BRANCHES`),
    and a linter that cannot tell a code reference from a published name
    must not grade code at all — so this one grades only prose.
    """
    lines = text.splitlines()
    wanted: set[int] = set()

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}

    # Docstrings: module / class / function, plus any bare string statement.
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                start = getattr(node.value, "lineno", None)
                end = getattr(node.value, "end_lineno", start)
                if start:
                    wanted.update(range(start, (end or start) + 1))

    # Comments: never reach the AST, so tokenize for them.
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                wanted.add(tok.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass

    return {n: lines[n - 1] for n in sorted(wanted) if 0 < n <= len(lines)}


def _allowed_by_context(line: str) -> bool:
    """True iff `line` sits in one of the documented legitimate contexts."""
    low = line.lower()
    if _INLINE_OK.search(low):
        return True
    return any(pattern.search(low) for pattern, _ in _ALLOW_CONTEXT)


def _relative(path: Path, repo: Path) -> str:
    try:
        return path.relative_to(repo).as_posix()
    except ValueError:
        return path.as_posix()


def _emit(out: list, violation_cls, severity: str, where: str, detail: str):
    """Append a PS-230 violation, carrying a per-finding severity override."""
    v = violation_cls("PS-230", where, detail)
    if severity != _DEFAULT_SEVERITY:
        try:
            v.severity_override = severity
        except (AttributeError, TypeError):  # pragma: no cover - stub classes
            pass
    out.append(v)
    return v


def _report_config_errors(repo: Path, config, violation_cls, out: list) -> None:
    """Surface rejected `audit.exemptions` entries for PS-230, at `E`."""
    from ._exemption_config_errors import report_exemption_config_errors

    report_exemption_config_errors(
        repo,
        config,
        "PS-230",
        lambda where, detail: _emit(
            out, violation_cls, _CONFIG_ERROR_SEVERITY, where, detail
        ),
    )


def check_ps230_naming_vocabulary(
    repo: Path,
    violation_cls: type,
    out: list,
    *,
    config=None,
) -> None:
    """Append PS-230 findings for retired role vocabulary in package prose.

    Parameters
    ----------
    repo : Path
        Repository root (the dir containing `src/`).
    violation_cls : type
        The auditor's `Violation` dataclass `(rule, where, detail)`.
    out : list
        Violations are appended in place (project-auditor convention).
    config : ProjectConfig, optional
        Pre-loaded project config. When omitted it is loaded from `repo` so
        the check honours `audit.exemptions` on its own.
    """
    if config is None:
        try:
            from .._config import load_config

            config = load_config(repo)
        except Exception:  # pragma: no cover - config is best-effort here
            config = None

    if config is not None:
        _report_config_errors(repo, config, violation_cls, out)

    exemption_for = getattr(config, "exemption_for", None)

    for path in _prose_files(repo):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        if path.suffix == ".md":
            prose = _prose_lines_markdown(text)
        else:
            prose = _prose_lines_python(text)

        rel = _relative(path, repo)

        for line_no, line in prose.items():
            if _allowed_by_context(line):
                continue
            for pattern, term, replacement in _BANNED:
                match = pattern.search(line)
                if match is None:
                    continue
                if exemption_for is not None and exemption_for(
                    "PS-230", rel, line_no
                ):
                    break
                _emit(
                    out,
                    violation_cls,
                    _DEFAULT_SEVERITY,
                    f"{path}:{line_no}",
                    (
                        f"retired term {match.group(0)!r} in prose (line "
                        f"{line_no}): {line.strip()[:120]!r}. Use "
                        f"{replacement}. {_FIX_HINT}"
                    ),
                )
                break


# Rule definition, CO-LOCATED with its check (the PS-222 / PS-223 / PS-226
# pattern). `_registry.py` merges `NAMING_VOCABULARY_RULES` at the BOTTOM of
# the module — the severity below is the one that ships, because
# `_SEVERITY_OVERRIDES` cannot reach a co-located rule.
#
# (code, section, message, severity, slug)
NAMING_VOCABULARY_RULES: list[tuple[str, str, str, str, str]] = [
    (
        "PS-230",
        "§2",
        (
            "retired role vocabulary in package prose (docstrings, comments, "
            "skills/markdown). The fleet fixes one pair per domain — "
            "credentials `primary/replica`, roles `controller/worker`, DB "
            "replication `node/origin` (operator decision 2026-08-11, "
            "`_skills/scitex-dev/25_naming-conventions.md`). PS-226..229 "
            "already make job NAMES and KINDS mechanical; this closes the "
            "other half, the WORDS, which were convention-only. Scope is "
            "prose ONLY: Python docstrings + comments and `.md` files under "
            "`src/`. Code is never graded, because an identifier or string "
            "literal may be a live contract (`master_host`) that a sweep "
            "cannot distinguish from a stale word. Legitimate uses are "
            "spared by a documented allowlist — OpenSSH `ControlMaster`, "
            "git's `master` branch, the `docs/MASTER/` path, published CLI/"
            "JSON tokens, and lines that are ABOUT the convention or record "
            "history. Fix: use the domain's word; if the occurrence is a "
            "published contract, alias it first (migration, not rename) and "
            "mark the line `naming-ok`. W on landing — the auditor runs "
            "fleet-wide and sibling repos are unswept; promote to E after a "
            "fleet sweep measures zero (PS-220/PR #406 lesson)."
        ),
        _DEFAULT_SEVERITY,
        "retired-naming-vocabulary",
    ),
]


__all__ = [
    "NAMING_VOCABULARY_RULES",
    "check_ps230_naming_vocabulary",
]

# EOF
