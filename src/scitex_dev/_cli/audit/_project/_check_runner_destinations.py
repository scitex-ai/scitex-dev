# -*- coding: utf-8 -*-
"""PS-224 — every workflow's ``runs-on`` must name a REGISTERED destination.

Operator design, 2026-07-24:

    「食い違いがあったらすぐエラー、それで終わり」
    — a mismatch is an error, immediately, and that's the end of it.

scitex-dev owns the single registry of machines (``scitex_dev.hosts``,
backed by ``~/.scitex/dev/hosts.yaml``). That registry is the SOURCE OF
TRUTH for legal CI runner destinations: each machine records, under
``runner_labels:``, the label sets its self-hosted GitHub Actions runners
actually serve. Every workflow names its destination explicitly, and a
destination that does not match the registry is an **ERROR (E)**.

The failure this kills
----------------------
Three scheduled runs (scitex-io, scitex-hub, scitex-writer) sat
UNDISPATCHED from 2026-05-15 — ``updated_at == created_at``, never picked
up — because they requested a runner label set that no machine serves,
while 17 runners sat online and idle. Nothing failed: GitHub queues an
unmatchable job indefinitely rather than rejecting it, so the workflow
looked merely slow for months.

This rule is deliberately **STATIC**. It fires before merge, from the
YAML text plus the registry file — no Actions API call, no dispatch-time
router, no capacity dependency. Under this rule those three workflows
could never have merged.

Why severity E, with no ratchet
-------------------------------
Three softeners were considered and REJECTED by the operator, for reasons
worth recording so they are not reintroduced under another name:

* **No new-vs-old ratchet / grandfathering.** 「昔だろうが今だろうが問題点
  は問題点」 — an old problem is a problem. It is also structurally broken:
  the baseline is computed by running the CURRENT rules against the OLD
  tree, so a NEWLY ADDED rule flags the old tree too, every hit classifies
  as pre-existing, and the new rule is suppressed forever. That mechanism
  would neutralise every future standard.
* **No severity W.** W never affects the exit code (``_audit.py``:
  ``exit_code = 1 if n_errors > 0 else 0``), which is exactly why the
  sibling PS-169 rule fires hundreds of times fleet-wide and has never
  once failed a build.
* **No blanket suppression flag.** Individual, reasoned exemptions in
  ``.scitex/dev/config.yaml`` under ``audit.exemptions`` only
  (constitution §2) — an exemption must state WHY. See "Exemptions"
  below for the exact, JOB-QUALIFIED spelling.

A fleet-wide red is the INTENDED outcome: 「全て赤でいいと思います。正直に
赤から始めて、レッドスタート」. Red is the honest measurement; the list is
then burned down. Nothing here exists to reduce the initial red count.

What counts as a violation
--------------------------
1. **Unserved destination** — the job's labels resolve concretely, and no
   registered machine advertises all of them. Includes every
   GitHub-hosted image (``ubuntu-latest`` & co.), which by construction is
   in no machine's ``runner_labels``.
2. **Unresolvable destination** — ``runs-on`` is an expression with no
   static literal to read (e.g. a bare ``${{ vars.RUNNER }}`` or
   ``${{ matrix.os }}``). The mandate is that every workflow **names its
   destination explicitly**; a destination that cannot be read statically
   does not name one. This is the deliberate difference from PS-169,
   which leaves unresolvable runners alone: without it, wrapping any
   label in a variable is a universal bypass and the rule is neutralised.
3. **Unparseable workflow** — the file is not valid YAML, so its
   destinations cannot be verified at all. Reported rather than skipped:
   a check that could not run must never report what a check that passed
   reports.

The one case that is NOT a violation: a job with no ``runs-on`` at all.
That is a ``uses:`` job delegating to a reusable workflow, which carries
its own ``runs-on`` in ITS file. **Known static boundary:** a repo can
therefore inherit a destination from e.g. ``scitex-ai/.github`` that its
own YAML never mentions, and no string search of this repo can see it.
Auditing the called repo covers it — this rule does not.

Registry floor (shipped seed) and the gap guard
-----------------------------------------------
The registry is resolved from a host's user-state ``~/.scitex/dev/hosts.yaml``.
That file can legitimately contribute NO runner destinations — it is
absent on a fresh host, or a STALE pre-``runner_labels`` copy that
``create_default_hosts_yaml`` will not refresh (it only writes when the
file is missing). If that emptiness were read as "no runners exist", every
workflow in the fleet would turn red for a reason that has nothing to do
with the workflows.

scitex-dev owns the single machine registry and SHIPS the canonical seed
in its own code (``scitex_dev.hosts._seed._DEFAULT_HOSTS_YAML``), so this
rule uses that seed as a FLOOR: when the user-state registry contributes
no destinations, it validates against
``packaged_default_runner_destinations()`` instead. A stale or empty local
file therefore cannot erase the shipped truth. This is not a softening —
the floor supplies REAL, measured destinations, and a job whose labels no
registered runner serves still errors.

Only if EVEN the shipped seed carries no destinations (a code regression,
never a deployment state) does the rule emit ONE finding naming the
registry file and suppress the per-job noise — an honest "I could not
check this", not a green.

Exemptions — JOB-QUALIFIED, and a reason is MANDATORY
-----------------------------------------------------
Some jobs genuinely cannot run on a self-hosted node (a matrix of Emacs
versions, `apt-get`/root installs, Docker service containers, a body that
is entirely `gh` CLI). The only sanctioned opt-out is ``audit.exemptions``
in ``.scitex/dev/config.yaml``, keyed by rule code, with a MANDATORY
written ``reason``::

    audit:
      exemptions:
        PS-224:
          - path: .github/workflows/test.yml::test
            line: 0
            reason: "setup-emacs installs Nix (needs root) + a 5-version matrix"

**The ``path`` is the SITE KEY, not a file path**: ``<workflow-path>::<job-id>``
— the exact string this rule prints as the finding's location, so it can be
copied verbatim from the audit output. It is job-qualified BY DESIGN: a
bare file path would also exempt every OTHER job in the same file, so a
migrated job that later regressed would go unnoticed. One entry exempts
exactly one job.

``line: 0`` — PS-224 findings are per-JOB, not per-line, so every exemption
pins line 0 (same contract as PS-222). The whole-file findings (unreadable
or unparseable workflow) are keyed on the BARE workflow path, since they
name no job.

A missing, blank or whitespace-only ``reason`` is REJECTED by the loader:
the entry exempts NOTHING (the job still errors) and the rejection is
reported at ``E`` by the shared config-error arm — an exemption with no
stated reason is exactly the unexamined suppression this rule exists to
catch. There is no ``# noqa`` hatch and no blanket flag.

Supported ``runs-on`` forms
---------------------------
The scalar / list / ``labels:`` mapping / ``fromJSON(... || '[...]')``
expression forms are all resolved — see :mod:`._runs_on_parsing`, which owns
that pure parsing layer. The fleet idiom's LITERAL FALLBACK is what gets
validated: it is what actually runs whenever the ``CI_RUNS_ON`` repo/org
variable is unset, which is the common case.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ._runs_on_parsing import describe_destinations as _describe
from ._runs_on_parsing import resolve_destination as _resolve_destination
from ._runs_on_parsing import workflow_files as _workflow_files

_RULE = "PS-224"

#: Co-located rule definition, merged by `_registry` on the same terms as
#: LOGS_PATH_RULES / CONFIG_LAYOUT_RULES. Severity lives HERE, in the tuple —
#: `_registry._SEVERITY_OVERRIDES` is a silent no-op for a co-located rule.
#:
#: **E on day one, no ratchet, no bake-in W.** See the module docstring for
#: why each softener was rejected; the short version is that W cannot fail a
#: build and a new-vs-baseline ratchet suppresses any NEWLY ADDED rule forever.
RUNNER_DESTINATION_RULES: list[tuple[str, str, str, str, str]] = [
    (
        _RULE,
        "§1",
        (
            "GitHub Actions job targets a runner destination that the "
            "scitex-dev MACHINE REGISTRY does not serve. scitex-dev owns the "
            "single registry of machines (`scitex_dev.hosts`, backed by "
            "`~/.scitex/dev/hosts.yaml`); each machine's `runner_labels:` "
            "records the label sets its self-hosted runners actually serve, "
            "and that registry is the source of truth for legal CI runner "
            "destinations. A job whose labels no machine advertises is not "
            "slow — it is UNDELIVERABLE: GitHub queues an unmatchable job "
            "indefinitely rather than rejecting it, which is how three "
            "scheduled runs (scitex-io, scitex-hub, scitex-writer) sat "
            "undispatched from 2026-05-15 (`updated_at == created_at`) while "
            "17 runners were online and idle. A job that does not name its "
            "destination statically (a bare `${{ vars.X }}` / "
            "`${{ matrix.os }}`) is flagged for the same reason: a "
            "destination that cannot be read cannot be checked, and would "
            "otherwise be a universal bypass. Static rule — fires pre-merge "
            "from the workflow YAML plus the registry file, with no Actions "
            "API call and no capacity dependency. Fix by targeting a "
            "registered destination, or by registering the machine that "
            "serves the label set. A job that genuinely cannot run on any "
            "registered machine is exempted ONE JOB AT A TIME in "
            "`.scitex/dev/config.yaml` under `audit.exemptions` -> `PS-224`, "
            "with `path: <workflow-path>::<job-id>` (the JOB-QUALIFIED site "
            "key this rule prints, so a file-wide exemption cannot hide a "
            "sibling job), `line: 0`, and a mandatory `reason:` "
            "(constitution §2) — a blank reason exempts nothing."
        ),
        "E",
        "runner-destination-unregistered",
    ),
]


#: Separator between a workflow path and a job id in an exemption SITE KEY —
#: `.github/workflows/test.yml::test`. Findings are per-JOB, so a bare path
#: would OVER-EXEMPT: one file routinely holds a job that must stay hosted
#: AND a job already migrated. Human-writable and greppable on purpose.
_SITE_SEP = "::"

#: PS-224 findings are per-JOB, not per-line, so both the emitted site and
#: any `audit.exemptions` entry pin line 0 (same contract as PS-222).
_NO_LINE = 0


def _site(rel: str, job_id: str | None = None) -> str:
    """Site key for a finding: ``path`` or ``path::job-id``.

    This exact string is BOTH the finding's reported location AND what an
    ``audit.exemptions`` entry's ``path`` must spell, so the instruction a
    user reads is the instruction that works.
    """
    return rel if job_id is None else f"{rel}{_SITE_SEP}{job_id}"


def _exempt_hint(site: str) -> str:
    """The copy-pasteable exemption recipe for one site (reason MANDATORY)."""
    return (
        " If this job genuinely cannot run on any registered machine, exempt "
        "THIS JOB (never the whole file) in `.scitex/dev/config.yaml` under "
        f"`audit: exemptions: PS-224:` with `path: {site}`, `line: 0` and a "
        "`reason:` saying why — the reason is mandatory (constitution §2), "
        "and a blank one exempts nothing."
    )


def check_ps224_runner_destinations(
    repo: Path,
    violation_cls: type,
    out: list,
    *,
    hosts_path: str | Path | None = None,
    floor_destinations: list[tuple[str, frozenset[str]]] | None = None,
    config=None,
) -> None:
    """Append PS-224 violations for unregistered CI runner destinations.

    Parameters
    ----------
    repo : Path
        Repository root (the dir containing ``.github/workflows/``).
    violation_cls : type
        The auditor's ``Violation`` dataclass ``(rule, where, detail)``.
    out : list
        Violations are appended in place (project-auditor convention).
    hosts_path : str | Path | None
        Explicit override for the machine registry's ``hosts.yaml``. The
        real audit leaves this ``None`` (canonical user-scope registry);
        tests pass a real temp file, so this is a file-path seam rather
        than a patch point — no mocks.
    floor_destinations : list[tuple[str, frozenset[str]]] | None
        Override for the SHIPPED-seed floor used when the user registry
        contributes no destinations. The real audit leaves this ``None``
        (the floor is read from
        :func:`scitex_dev.hosts.packaged_default_runner_destinations`);
        tests pass a real list — e.g. ``[]`` to exercise the seed-empty gap
        branch — so this is a value seam, not a patch point (no mocks).
    config : ProjectConfig, optional
        Pre-loaded project config. When omitted it is loaded from ``repo``
        so the check honours ``audit.exemptions`` on its own; passing it in
        lets a caller that already loaded the config avoid a second read.
        Exemption site keys are JOB-QUALIFIED (``path::job-id``) — see the
        module docstring's "Exemptions" section.
    """
    workflows = _workflow_files(repo)
    if not workflows:
        return

    if config is None:
        try:
            from .._config import load_config

            config = load_config(repo)
        except Exception:  # pragma: no cover - config is best-effort here
            config = None

    exemption_for = getattr(config, "exemption_for", None)

    def _exempt(site: str) -> bool:
        """True iff an ACCEPTED (reasoned) exemption covers exactly ``site``.

        A rejected entry — blank/missing ``reason`` — never matches, by
        construction in the loader, and is reported at ``E`` by the shared
        config-error arm. So a reasonless exemption suppresses nothing.
        """
        if exemption_for is None:
            return False
        return bool(exemption_for(_RULE, site, _NO_LINE))

    from ....hosts import get_hosts_yaml_path
    from ....hosts import list_runner_destinations
    from ....hosts import packaged_default_runner_destinations

    registry_file = get_hosts_yaml_path(hosts_path)
    destinations = list_runner_destinations(hosts_path=hosts_path)
    if not destinations:
        # FLOOR: a host's user-state registry contributes no destinations
        # (absent file, or a stale pre-`runner_labels` copy that
        # `create_default_hosts_yaml` won't refresh — it only writes when
        # the file is missing). scitex-dev owns the single registry and
        # SHIPS the canonical seed in its own code, so fall back to that
        # rather than reporting a gap: a stale/empty local file must not be
        # able to represent "no runners exist" and turn every workflow red.
        # Genuine mismatches still error below — the floor supplies REAL
        # measured destinations, not a blanket pass.
        destinations = (
            packaged_default_runner_destinations()
            if floor_destinations is None
            else floor_destinations
        )
    if not destinations:
        # Only reachable if EVEN the shipped seed carries no destinations —
        # a code regression, not a deployment state. Honest "could not
        # check", never a green: a check that could not run must not report
        # what a check that passed reports.
        out.append(
            violation_cls(
                _RULE,
                str(registry_file),
                "the machine registry records NO CI runner destinations, so "
                f"the {len(workflows)} workflow file(s) under "
                "`.github/workflows/` could not be validated. Add a "
                "`runner_labels:` block to each machine that hosts a "
                "self-hosted runner, listing the EFFECTIVE label set of each "
                "runner (as `gh api .../actions/runners` reports it, "
                "auto-assigned `self-hosted`/OS/arch labels included), e.g.\n"
                "  spartan:\n"
                "    runner_labels:\n"
                "      - [self-hosted, Linux, X64, spartan-cpu, scitex-ci]",
            )
        )
        return

    legal = _describe(destinations)

    for path in workflows:
        # POSIX-normalised: the site key is compared against a config-written
        # `path`, which the loader also normalises to forward slashes.
        rel = path.relative_to(repo).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            if _exempt(_site(rel)):
                continue
            out.append(
                violation_cls(
                    _RULE,
                    rel,
                    f"workflow is unreadable ({exc}), so its runner "
                    "destination could not be validated against the machine "
                    "registry. A destination that cannot be checked is not a "
                    "destination that passed.",
                )
            )
            continue

        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            doc = None
            parse_error: str | None = str(exc).splitlines()[0]
        else:
            parse_error = None

        if not isinstance(doc, dict):
            # Whole-file finding: it names no job, so its site key is the
            # BARE workflow path (a job-qualified key cannot apply here).
            if _exempt(_site(rel)):
                continue
            out.append(
                violation_cls(
                    _RULE,
                    rel,
                    "workflow does not parse as a YAML mapping"
                    + (f" ({parse_error})" if parse_error else "")
                    + ", so its runner destination could not be validated "
                    "against the machine registry. Fix the YAML — a "
                    "destination that cannot be read is not a destination "
                    "that passed.",
                )
            )
            continue

        jobs = doc.get("jobs")
        if not isinstance(jobs, dict):
            continue

        for job_id, job in jobs.items():
            if not isinstance(job, dict) or "runs-on" not in job:
                # No `runs-on` == a `uses:` job delegating to a reusable
                # workflow, which carries its own destination in ITS file.
                # See the module docstring's known-static-boundary note.
                continue
            # Per-JOB site key. A bare path would OVER-EXEMPT: the same file
            # routinely holds a job that must stay hosted AND a job already
            # migrated, and exempting the file would silently cover both.
            site = _site(rel, str(job_id))
            runs_on = job["runs-on"]
            labels = _resolve_destination(runs_on)

            if labels is None:
                if _exempt(site):
                    continue
                out.append(
                    violation_cls(
                        _RULE,
                        site,
                        f"job `{job_id}` does not name its runner destination "
                        f"explicitly: `runs-on: {runs_on}` has no statically "
                        "readable label set. Every workflow must name a "
                        "destination the machine registry can be checked "
                        "against — otherwise a variable is a universal "
                        "bypass. Use a literal label list, or the fleet idiom "
                        "whose `|| '[...]'` fallback IS the literal: "
                        "`runs-on: ${{ fromJSON(vars.CI_RUNS_ON || "
                        "'[\"self-hosted\",\"Linux\",\"X64\",\"scitex-ci\"]') "
                        f"}}`. Registered destinations: {legal}."
                        + _exempt_hint(site),
                    )
                )
                continue

            # Match against the RESOLVED destinations (user-state, or the
            # shipped floor when user-state was empty) — not a fresh
            # `find_runner_host`, which would re-read user-state and ignore
            # the floor. Same rule as `HostRecord.serves`: a runner serves
            # the job when its label set contains every requested label.
            wanted = frozenset(labels)
            if any(wanted <= served for _host, served in destinations):
                continue

            if _exempt(site):
                continue

            out.append(
                violation_cls(
                    _RULE,
                    site,
                    f"job `{job_id}` targets `[{', '.join(labels)}]`, which NO "
                    f"registered machine serves (registry: {registry_file}). "
                    "GitHub does not reject an unmatchable job — it queues it "
                    "forever, so this never fails, it just never runs. Point "
                    "the job at a registered destination, or register the "
                    "machine that serves this label set in the registry's "
                    f"`runner_labels:`. Registered destinations: {legal}."
                    + _exempt_hint(site),
                )
            )


# EOF
