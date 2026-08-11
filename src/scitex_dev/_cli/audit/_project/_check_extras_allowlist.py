# -*- coding: utf-8 -*-
"""PS-225 — extra NAMES are restricted to ``{all, dev, docs}``.

Operator ruling, 2026-08-02:

    「dev docs all だけ例外に許されるエクストラの名前」
    — dev, docs and all are the only permitted extra names.

    「all or nothing で。torch, browser, slurm のインストールを嫌がる人
      っています？そんな人は自分でどうやって省くかわかる」
    — all or nothing; anyone who minds knows how to omit it themselves.

There are exactly two installs:

    pip install <pkg>          # minimum — core dependencies only
    pip install <pkg>[all]     # everything

Nothing in between. A per-feature menu is what this rule deletes.

The failure this kills
----------------------
2026-08-02, fleet-wide: container definitions pinned ``scitex-cards[mcp]``.
That extra does not pull ``psycopg``, so every agent came up with a card
store that could not reach Postgres, and the board was down for hours.

Nobody was careless. The pin was chosen from the menu the package offered,
it was the pin the package's OWN rollout documentation prescribed, and two
agents diagnosing the outage each recommended another partial set within the
hour — one of them on image-size grounds, an hour after diagnosing the first
one. The failure mode survives people who have just been burned by it, which
is why it needs a mechanical barrier rather than a written warning
(constitution §6).

Why the NAMES and not the pins
------------------------------
Pins are the symptom. As long as a per-feature extra EXISTS, someone will
pin it — and the existence of one teaches the next person that adding
another is normal. The operator put it exactly:

    「docs あるなら新しいエクストラ作ろ、ってならなければ良いです」

So this rule governs the one place the menu can be created.

Why there is no exemption mechanism
-----------------------------------
One was proposed (by this auditor's author, and independently by
scitex-cards) on the grounds that a strict set forces heavy dependencies —
``torch`` is an optional extra in 6 packages, ``browser`` in 3 — onto every
install. **That premise is false, and the check is one line of thought: the
opt-out already exists and is the BARE install.** Core only, no ``[all]``,
no torch.

An exemption mechanism would have re-legalised the exact construct this rule
deletes, one written reason at a time. Recording it here because both of us
designed for a pain neither had checked was real.

What this rule does NOT catch
-----------------------------
A pin naming an extra that no longer exists. Measured 2026-08-02::

    uv pip install --dry-run 'scitex-dev[thisextradoesnotexist]'
    warning: The package ... does not have an extra named `...`
    EXIT=0

**A warning, exit 0.** So after ``mcp`` is deleted, a surviving
``scitex-cards[mcp]`` pin still installs, warns into a log nobody reads, and
omits the capability — this outage, one layer over. PS-225 stops the extra
from being CREATED; catching pins that already exist is a separate check over
``.md`` / ``.yml`` / ``.def`` / ``.py``. Both are required; neither is
sufficient.

Remedy
------
Move the extra's requirements into ``[project.dependencies]`` (core), or
into ``all``. If a capability's absence does not NAME ITSELF at the point of
use — ``ModuleNotFoundError: torch`` names itself; psycopg's absence
surfaced as "the database does not exist" — it belongs in core, not in
``all``.
"""

from __future__ import annotations

from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 3.10 and older
    import tomli as tomllib  # type: ignore[no-redef]

#: The only permitted extra names. Operator ruling 2026-08-02.
ALLOWED_EXTRAS = frozenset({"all", "dev", "docs"})

_RULE = "PS-225"

#: ``(code, section, message, severity, slug)`` — merged into the audit rule
#: registry the same way ALL_CLOSURE_RULES / PRINT_FORBIDDEN_RULES are.
#:
#: Severity W for the rollout, per ADR-0005: a rule that lands as an ERROR on
#: every package at once is a rule that gets suppressed rather than obeyed.
#: Promote to E once the fleet has converted.
EXTRAS_ALLOWLIST_RULES: list[tuple[str, str, str, str, str]] = [
    (
        _RULE,
        "§1",
        "extra name outside the {all, dev, docs} allowlist",
        "W",
        "extra-name-not-allowlisted",
    ),
]


def _parse_pyproject(repo: Path) -> dict | None:
    """Return the parsed ``pyproject.toml``, or None when absent/unreadable."""
    path = repo / "pyproject.toml"
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def check_ps225_extras_allowlist(
    repo: Path,
    violation_cls: type,
    out: list,
) -> None:
    """Append PS-225 violations for extra names outside the allowlist.

    Parameters
    ----------
    repo : Path
        Repository root (the dir containing ``pyproject.toml``).
    violation_cls : type
        The auditor's ``Violation`` dataclass ``(rule, where, detail)``.
    out : list
        Violations are appended in place (project-auditor convention).
    """
    meta = _parse_pyproject(repo)
    if meta is None:
        return
    project = meta.get("project")
    if not isinstance(project, dict):
        return
    optional = project.get("optional-dependencies")
    if not isinstance(optional, dict):
        return

    offenders = sorted(name for name in optional if name not in ALLOWED_EXTRAS)
    if not offenders:
        return

    where = str(repo / "pyproject.toml")
    for name in offenders:
        out.append(
            violation_cls(
                _RULE,
                where,
                (
                    f"`[project.optional-dependencies.{name}]` is not an "
                    f"allowed extra. Only {sorted(ALLOWED_EXTRAS)} may be "
                    "declared — there are exactly two installs, "
                    "`pip install <pkg>` (core only) and "
                    "`pip install <pkg>[all]` (everything), with nothing in "
                    "between. A per-feature extra is a menu, and a menu is "
                    "what let container definitions pin `scitex-cards[mcp]` "
                    "and lose psycopg fleet-wide on 2026-08-02. "
                    f"FIX: move `{name}`'s requirements into "
                    "`[project.dependencies]` (core) or into `all`. If the "
                    "capability's absence would NOT name itself at the point "
                    "of use, it belongs in core: `ModuleNotFoundError: torch` "
                    "names itself, whereas the missing psycopg surfaced as "
                    "'the database does not exist'. There is deliberately NO "
                    "exemption mechanism — the opt-out is the bare install."
                ),
            )
        )


# EOF
