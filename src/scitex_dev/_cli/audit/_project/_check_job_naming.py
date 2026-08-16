# -*- coding: utf-8 -*-
"""PS-226..PS-229 — the fleet-wide ``JobSpec`` declaration convention.

Operator ruling, 2026-08-11 (Telegram):

    「はい、他のパッケージもこれがルールです。scitex-dev の auditor に
      入れておいてください」
    — yes, this is the rule for the other packages too; put it in
      scitex-dev's auditor.

    「全部一新して統一するという話です」
    — the point is to renew and unify all of it.

Four invariants, one per rule:

======  ==================================================================
PS-226  ``name`` is hyphen-separated lowercase: ``^[a-z0-9]+(-[a-z0-9]+)*$``.
        No ``.``, no ``_``, no uppercase.                        **E**
PS-227  ``name`` is package-qualified — it starts with ``scitex-<pkg>-``.  **W**
PS-228  ``description`` is present and non-empty.                **E**
PS-229  ``kind``, when written as a literal, is one of the accepted
        spellings.                                               **E**
======  ==================================================================

Why a dotted name is a BUG, not a style preference
--------------------------------------------------
``JobSpec.name`` is not a label. It is the systemd unit filename, derived
VERBATIM at exactly one place —
``scitex_dev/jobs/_systemd.py::systemd_unit_name``::

    return f"{job.name}.timer" if job.kind == "timer" else f"{job.name}.service"

and written straight to ``~/.config/systemd/user/<that>`` by
``jobs/_ensure.py``. There is no sanitisation step, no dot-to-hyphen
mapping, no escaping. So the punctuation in the name IS the punctuation in
the filename, and systemd treats two filenames differing by one character
as two unrelated units.

The concrete failure this prevents is recorded in sac's own provider,
``scitex_agent_container/_jobs/_jobs_plugin.py`` (lines 136-160), which
declines to federate ``sac listen`` for precisely this reason:

    ``sac listen`` is DELIBERATELY NOT declared here, and adding it back
    would take the fleet's control plane down. […] a ``sac.listen``
    JobSpec materialises ``sac.listen.service`` — while the listen that
    actually runs on the host is ``sac-listen.service`` (a HYPHEN). […]
    it installs a SECOND one. Two units, both ``Restart=always``, both
    running ``sac listen``, both binding 127.0.0.1:7878.

    If this is ever federated, it must be named ``sac-listen`` (hyphen)
    so the derived unit is the one that already exists.

That is the whole rule in one sentence: **a dotted job name silently
fails to adopt the hand-written unit it was supposed to be, and installs
a duplicate supervisor instead.** The symptom is not an error — it is two
daemons where the operator expected one.

Severity, and why the two levels differ
---------------------------------------
PS-226/228/229 ship at **E**. The rename they demand is sanctioned
(operator, 2026-08-11) and the checks are mechanical.

PS-227 ships at **W**. Measured 2026-08-11 across every SciTeX package on
this machine, it flags **34 of 34** declared jobs — every dotted sac /
scitex-cards / scitex-hpc name AND every bare scitex-dev slug
(``ci-watch``, ``worktree-gc``, …). A rule that lands as an ERROR on
100% of the corpus is a rule that gets suppressed rather than obeyed
(ADR-0005). Promote it by changing ``"W"`` to ``"E"`` in
:data:`JOB_NAMING_RULES` below — and NOT via ``_SEVERITY_OVERRIDES``,
which is a silent no-op for co-located rules.

MIGRATION HAZARD — read before renaming anything
------------------------------------------------
Renaming a job renames its unit, and a renamed unit is a DIFFERENT FILE.
Install-before-uninstall therefore yields TWO supervisors, not one. Any
cutover must be ordered: **stop old -> remove old -> install new ->
verify exactly one**, and must be abort-safe at every step.

Two jobs make that ordering load-bearing rather than tidy:

* ``sac.accounts-refresh`` is the SOLE OAuth refresher for the whole
  fleet, and the refresh token is SINGLE-USE. Two refreshers racing
  revoke each other; zero expires every account within hours.
* ``sac-listen.service`` is a hand-written unit supervising the control
  plane right now — see the quote above.

This auditor deliberately ships NO auto-fix. It reports; a human (or a
card with its own proof) performs the cutover.

Detection is STATIC
-------------------
The check parses ``src/<pkg>/**/*.py`` with :mod:`ast` and never imports
the leaf — same discipline as PS-218/PS-219/PS-220. Only literal keyword
arguments are read; a computed ``name=`` expression is skipped rather
than guessed at, because a wrong guess in an auditor is worse than a
silent pass (a finding nobody can act on trains readers to ignore the
rule).

This scan intentionally covers scitex-dev's SECOND, local ``JobSpec``
class in ``_cli/cron/_jobs.py`` too. Those names are adapted into
canonical ``JobSpec`` objects by ``jobs.__init__._builtin_jobs()`` and
become real crontab identities, so they are governed by the same
convention. (The duplicate class itself is tracked separately as
``dev-two-jobspec-classes-ssot-violation-20260719``.)
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

#: The one legal shape for a ``JobSpec.name``: lowercase alphanumerics in
#: hyphen-separated segments. Derived from the ACTUAL corpus, not invented —
#: measured 2026-08-11 over all 34 declared jobs, the character set in use is
#: exactly ``[a-z]``, ``-`` and ``.``; there are no digits, no underscores and
#: no uppercase anywhere. Digits are admitted because a future ``…-v2`` slug
#: is reasonable and harmless in a unit filename; ``.`` and ``_`` are not.
JOB_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


#: Every ``kind`` spelling ``JobSpec`` accepts at construction. Imported from
#: the taxonomy rather than restated, so this rule can never disagree with the
#: dataclass it audits (the ``_jobs_audit`` "read the real thing" idiom).
def _accepted_kinds() -> frozenset[str]:
    from scitex_dev.jobs._kinds import ACCEPTED_KINDS

    return ACCEPTED_KINDS


#: ``(code, section, message, severity, slug)`` — merged into the audit rule
#: registry the same way EXTRAS_ALLOWLIST_RULES / RUNNER_DESTINATION_RULES are.
#: Severity lives HERE, in the tuple, never in ``_SEVERITY_OVERRIDES``: an
#: override for a co-located rule is a silent no-op (see the note beside
#: ``_rules.__init__._patch``).
JOB_NAMING_RULES: list[tuple[str, str, str, str, str]] = [
    (
        "PS-226",
        "§1",
        "JobSpec name is not hyphen-separated lowercase (a '.' or '_' "
        "silently derives a systemd unit filename that adopts nothing)",
        "E",
        "job-name-not-hyphenated",
    ),
    (
        "PS-227",
        "§1",
        "JobSpec name is not package-qualified as `scitex-<pkg>-<name>`",
        "W",
        "job-name-not-package-qualified",
    ),
    (
        "PS-228",
        "§1",
        "JobSpec declares no description (it is the only text `list` and "
        "`systemctl status` have to identify the unit by)",
        "E",
        "job-description-missing",
    ),
    (
        "PS-229",
        "§1",
        "JobSpec kind is outside the accepted vocabulary",
        "E",
        "job-kind-not-accepted",
    ),
    (
        "PS-232",
        "§1",
        "the JobSpec scan could not resolve the source package, so it "
        "graded NOTHING — this is not a clean result, it is a rule that "
        "did not run",
        "W",
        "job-scan-found-no-source-package",
    ),
]


def expected_job_prefix(distribution: str) -> str:
    """Return the ``scitex-<pkg>-`` prefix every job of *distribution* needs.

    Derived from the distribution name so the rule never has to guess a
    package's short alias. ``scitex-agent-container`` yields
    ``scitex-agent-container-``; a hypothetical bare ``foo`` yields
    ``scitex-foo-``.

    Deliberately NOT derived from the CLI binary name: ``sac`` is
    scitex-agent-container's binary, and a convention keyed on binaries
    would make the expected prefix unknowable from the repo alone.
    """
    dist = distribution.strip().lower()
    if dist.startswith("scitex-"):
        return f"{dist}-"
    return f"scitex-{dist}-"


def _literal_kwargs(call: ast.Call) -> dict[str, object]:
    """Return the subset of *call*'s keywords whose values are literals.

    A non-literal (an f-string, a name, a call) is OMITTED rather than
    approximated. The caller distinguishes "absent" from "present but not
    statically knowable" by consulting :func:`_kwarg_names`.
    """
    out: dict[str, object] = {}
    for kw in call.keywords:
        if kw.arg is None:
            continue
        if isinstance(kw.value, ast.Constant):
            out[kw.arg] = kw.value.value
    return out


def _kwarg_names(call: ast.Call) -> set[str]:
    """Every keyword name passed to *call*, literal or not."""
    return {kw.arg for kw in call.keywords if kw.arg is not None}


def _is_jobspec_call(node: ast.AST) -> bool:
    """True for ``JobSpec(...)`` and ``<mod>.JobSpec(...)``."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "JobSpec"
    if isinstance(func, ast.Attribute):
        return func.attr == "JobSpec"
    return False


def _iter_job_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if _is_jobspec_call(node):
            yield node


def _python_files(src_pkg: Path):
    return sorted(p for p in src_pkg.rglob("*.py") if p.is_file())


def check_job_naming(
    repo: Path,
    distribution: str,
    violation_cls: type,
    out: list,
) -> None:
    """Append PS-226..PS-229 findings for every ``JobSpec(...)`` in *repo*.

    Parameters
    ----------
    repo : Path
        Repository root (the dir containing ``pyproject.toml``).
    distribution : str
        The distribution name, e.g. ``"scitex-agent-container"``. Used to
        derive the expected ``scitex-<pkg>-`` prefix for PS-227.
    violation_cls : type
        The auditor's ``Violation`` dataclass ``(rule, where, detail)``.
    out : list
        Violations are appended in place (project-auditor convention).
    """
    from ._discovery import _src_pkg_dir

    src_pkg = _src_pkg_dir(repo, distribution)
    if src_pkg is None:
        # PS-232 — SAY SO. This used to be a bare `return`, and a bare
        # return here is indistinguishable at every downstream layer from
        # "scanned the package, found nothing wrong": zero files examined,
        # zero findings appended, a clean summary line.
        #
        # scitex-agent-container hit the consequence from outside on
        # 2026-08-15: PS-226 fired on their tree locally and reported
        # nothing in CI, which is the WRONG DIRECTION for the file-set
        # divergence we had just root-caused, because CI walks a superset.
        # A rule that grades nothing explains that asymmetry.
        #
        # TWO DISTINCT SITUATIONS, AND ONLY ONE IS A DEFECT:
        #   - no `pyproject.toml`  -> this is not a Python distribution, so
        #     a JobSpec scan does not APPLY. Silence is correct, and the
        #     surrounding test section is right that "the check must never
        #     be the thing that breaks the audit".
        #   - `pyproject.toml` present -> the repo CLAIMS to be a
        #     distribution and the scan still could not find its source.
        #     That is a rule that failed to run, and it must say so.
        #
        # Severity W, not E, and the reason is a limit on my own evidence
        # rather than caution for its own sake. I measured 22 of 23
        # packages under ~/proj resolving — but I selected that population
        # BY the presence of pyproject.toml, which biases it toward exactly
        # the repos that resolve. A flat-layout distribution elsewhere in
        # the fleet could resolve to None legitimately, and E would redden
        # it on the strength of a sample that could not have contained it.
        # W still breaks the SILENCE, which is the actual defect: the run
        # now says it graded nothing instead of implying it found nothing.
        # Promote to E once the population has been measured without that
        # filter.
        if (repo / "pyproject.toml").exists():
            out.append(
                violation_cls(
                    "PS-232",
                    str(repo),
                    f"could not resolve the source package for "
                    f"{distribution!r} under {repo}; the JobSpec scan "
                    "examined 0 files and reported 0 violations, which is "
                    "NOT a pass. Check that the distribution name matches "
                    "the package directory and that --path names the tree "
                    "you meant.",
                )
            )
        return

    accepted = _accepted_kinds()
    prefix = expected_job_prefix(distribution)

    for path in _python_files(src_pkg):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError):
            # An unreadable/unparseable file is not this rule's business —
            # PS-2xx siblings skip it the same way, and the syntax error
            # itself surfaces loudly everywhere else.
            continue
        for call in _iter_job_calls(tree):
            where = f"{path}:{call.lineno}"
            _check_one_call(call, where, prefix, accepted, violation_cls, out)


def _check_one_call(
    call: ast.Call,
    where: str,
    prefix: str,
    accepted: frozenset[str],
    violation_cls: type,
    out: list,
) -> None:
    literals = _literal_kwargs(call)
    present = _kwarg_names(call)

    name = literals.get("name")
    if isinstance(name, str) and name:
        _check_name(name, where, prefix, violation_cls, out)

    _check_description(literals, present, name, where, violation_cls, out)

    kind = literals.get("kind")
    if isinstance(kind, str) and kind not in accepted:
        out.append(
            violation_cls(
                "PS-229",
                where,
                (
                    f"JobSpec(kind={kind!r}) is not an accepted kind. "
                    f"Valid: {sorted(accepted)} — `service`, `timer` and "
                    "`cron` are the STORED kinds, `daemon` and `periodic` "
                    "are intent spellings normalised into them by "
                    "`scitex_dev.jobs._kinds.canonical_kind`. A kind outside "
                    "this set is not merely rejected at construction: a "
                    "CONSUMER that filters on one can never match, which is "
                    "how `sac dev systemd list` (filtering kind='systemd') "
                    "showed zero jobs while four sac timers were declared "
                    "and running."
                ),
            )
        )


def _check_name(
    name: str,
    where: str,
    prefix: str,
    violation_cls: type,
    out: list,
) -> None:
    if not JOB_NAME_RE.match(name):
        suggestion = re.sub(r"[._]+", "-", name).lower()
        out.append(
            violation_cls(
                "PS-226",
                where,
                (
                    f"JobSpec(name={name!r}) is not hyphen-separated "
                    f"lowercase (required shape: {JOB_NAME_RE.pattern}). "
                    "The name is NOT a label — `jobs/_systemd.py::"
                    "systemd_unit_name` derives the unit filename from it "
                    f"VERBATIM, so this one becomes `{name}.service` / "
                    f"`{name}.timer` on disk with no sanitisation. A dotted "
                    "name therefore FAILS TO ADOPT the hand-written unit it "
                    "was meant to be and systemd installs a SECOND, "
                    "unrelated one: that is exactly why sac refuses to "
                    "federate `sac listen` as `sac.listen` — the live unit "
                    "is `sac-listen.service` (hyphen), and the duplicate "
                    "would give two `Restart=always` supervisors both "
                    f"binding the same port. FIX: rename to {suggestion!r} "
                    "— but a rename is a UNIT MIGRATION, so order it "
                    "stop-old -> remove-old -> install-new -> verify-exactly-"
                    "one. Never install first: `sac.accounts-refresh` is the "
                    "fleet's SOLE OAuth refresher on a SINGLE-USE token, and "
                    "two racing refreshers revoke each other."
                ),
            )
        )
        return
    if not name.startswith(prefix):
        out.append(
            violation_cls(
                "PS-227",
                where,
                (
                    f"JobSpec(name={name!r}) is not package-qualified — "
                    f"expected the form `{prefix}<name>`. Job names share "
                    "ONE flat namespace: `discover_jobs()` de-duplicates "
                    "strictly by name and the FIRST provider wins, dropping "
                    "the loser with nothing but a log line. Two packages "
                    "that both ship a plausible bare slug (`worktree-gc` "
                    "exists today as both a scitex-dev built-in and "
                    "`sac.worktree-gc`) are one rename away from silently "
                    "shadowing each other. FIX: rename to "
                    f"{prefix + name!r}, ordering the unit migration "
                    "stop-old -> remove-old -> install-new -> verify."
                ),
            )
        )


def _check_description(
    literals: dict[str, object],
    present: set[str],
    name: object,
    where: str,
    violation_cls: type,
    out: list,
) -> None:
    """PS-228 — a description must be declared AND say something.

    A ``description=`` whose value is not a literal (a variable, an
    f-string) is accepted: it is present, and this rule refuses to guess
    what it evaluates to.
    """
    if "description" not in present:
        detail_subject = f"JobSpec(name={name!r})" if name else "JobSpec(...)"
        out.append(
            violation_cls(
                "PS-228",
                where,
                (
                    f"{detail_subject} declares no `description=`. It is the "
                    "only human text the job carries: it becomes the systemd "
                    "unit's `Description=` (`jobs/_systemd.py`) and the "
                    "`ecosystem list` column an operator reads at 3am. FIX: "
                    'add `description="<what this does, and why it exists>"`.'
                ),
            )
        )
        return
    value = literals.get("description")
    if isinstance(value, str) and not value.strip():
        detail_subject = f"JobSpec(name={name!r})" if name else "JobSpec(...)"
        out.append(
            violation_cls(
                "PS-228",
                where,
                (
                    f"{detail_subject} has an EMPTY `description=`. An empty "
                    "string satisfies the dataclass and then renders as the "
                    "job's own name in the generated unit "
                    "(`Description={job.description or job.name}`), so the "
                    "operator reading `systemctl --user status` learns "
                    "nothing the filename did not already say. FIX: write "
                    "one sentence saying what the job does and why."
                ),
            )
        )


__all__ = [
    "JOB_NAME_RE",
    "JOB_NAMING_RULES",
    "check_job_naming",
    "expected_job_prefix",
]

# EOF
