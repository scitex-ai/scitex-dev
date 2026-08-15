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

A job with no ``runs-on`` is a ``uses:`` delegation carrying its own
destination in ITS file, and is normally NOT a violation — except when the
caller is attacker-triggerable AND passes ``secrets: inherit``. That pair
is decidable from the caller alone and IS flagged; measured live on the
org template. **Known static boundary:** the destination itself still
lives in the callee, so a repo inherits a runner its YAML never names.

Registry floor (shipped seed) — a UNION, and the gap guard
----------------------------------------------------------
The registry is resolved from a host's user-state ``~/.scitex/dev/hosts.yaml``.
That file is MUTABLE PER HOST and is edited live (by the operator and by
agents), and it can legitimately contribute NO runner destinations — it is
absent on a fresh host, or a STALE pre-``runner_labels`` copy that
``create_default_hosts_yaml`` will not refresh (it only writes when the
file is missing).

scitex-dev owns the single machine registry and SHIPS the canonical seed
in its own code (``scitex_dev.hosts._seed._DEFAULT_HOSTS_YAML``), so this
rule validates against the **UNION** of that shipped seed and the
user-state registry, **always** — the seed is an unconditional FLOOR that
per-host state may only EXTEND, never subtract from. Destinations present
in both are de-duplicated (same host name + same label set), so the
"Registered destinations:" line lists each one once.

Why a UNION and not a fallback
------------------------------
The first implementation used the seed only as a FALLBACK — it read the
seed *when the user registry was empty*. That let per-host mutable state
SUBTRACT from the gate's ground truth: a host that registered even ONE
unrelated machine REPLACED the shipped seed entirely, hiding ``spartan``
and turning every correctly-migrated job red. Because the file is edited
live, the gate's verdict then moved under repos that changed nothing —
measured 2026-07-29 in scitex-agent-container, where the same tree passed
at 14:56 and failed after a 15:07 edit to ``hosts.yaml``, with no code
change in the audited area. A central gate must validate against SSOT data
shipped IN the package as a floor; per-host state may extend it, never
erase it.

The union is not a softening — both sides supply REAL, measured
destinations, and a job whose labels NEITHER side serves still errors.

Only if the floor AND the user-state registry are BOTH empty (a code
regression, never a deployment state) does the rule emit ONE finding
naming the registry file and suppress the per-job noise — an honest "I
could not check this", not a green.

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
          - path: .github/workflows/test.yml::<job-id-copied-from-the-audit-output>
            line: 0
            reason: "setup-emacs installs Nix (needs root) + a 5-version matrix"

**The ``path`` is the SITE KEY, not a file path**: ``<workflow-path>::<job-id>``
— the exact string this rule prints as the finding's location; run the audit
and paste THAT. The job id above is an OBVIOUS placeholder because a
plausible-looking one invites copying a job that does not exist in the target
repo, and an exemption keyed on a non-existent job exempts NOTHING while
reading as done. Job-qualified BY DESIGN: a bare file path would also exempt
every OTHER job in the same file, hiding a later regression in a migrated one.

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
from . import _workflow_exposure as _wx

_RULE = "PS-224"

#: GitHub-HOSTED images — a property of the PLATFORM, not machines we own, so
#: deliberately NOT registry entries: a host record would claim we operate
#: them. GitHub serves these on demand, always, so a job naming one can never
#: sit unmatched — the entire failure this rule exists to catch.
#:
#: Constitution §4 changed under a rule that was correct when written: hosted
#: is now the DEFAULT for public repos, so every COMPLIANT workflow named a
#: destination the registry did not know and PS-224 errored on compliance.
#: scitex-cards wrote EIGHT per-job exemptions to silence it (2026-08-02);
#: the operator ruled to fix the rule rather than accept them.
#:
#: A LITERAL SET, never a `ubuntu-*` prefix match: a typo'd `ubuntu-latests`
#: must still fail. A fuzzy match would forgive the mistake this is for.
GITHUB_HOSTED_LABELS: frozenset[str] = frozenset(
    {
        "ubuntu-latest", "ubuntu-24.04", "ubuntu-22.04",
        "ubuntu-24.04-arm", "ubuntu-22.04-arm",
        "windows-latest", "windows-2025", "windows-2022",
        "macos-latest", "macos-15", "macos-14", "macos-13",
    }
)


def _is_github_hosted(wanted: frozenset[str]) -> bool:
    """True when *wanted* is a hosted image and nothing else.

    `runs-on: ubuntu-latest` is the whole destination. A hosted label COMBINED
    with others (`[ubuntu-latest, self-hosted]`) is not hosted and is not
    accepted here — that combination matches no runner at all, which is
    precisely the unmatchable case this rule must keep reporting.
    """
    return len(wanted) == 1 and next(iter(wanted)) in GITHUB_HOSTED_LABELS

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


#: Site keys, the exemption recipe, and the floor∪user-state union live in
#: `_runner_destination_sites` (512-line budget). Re-exported here because the
#: site-key spelling `.github/workflows/test.yml::test` is a PUBLISHED
#: contract — it is what an `audit.exemptions` entry must spell — and tests
#: plus callers import these names from this module.
from ._runner_destination_sites import (  # noqa: E402,F401
    _NO_LINE,
    _SITE_SEP,
    _exempt_hint,
    _site,
    _union_destinations,
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
        Override for the SHIPPED-seed FLOOR, which is UNIONed with the
        user-state registry unconditionally. The real audit leaves this
        ``None`` (the floor is read from
        :func:`scitex_dev.hosts.packaged_default_runner_destinations`);
        tests pass a real list — e.g. ``[]`` for an EMPTY floor, which with
        an empty user registry exercises the gap branch — so this is a
        value seam, not a patch point (no mocks).
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

    if config is not None:
        # The arm the docstring promised: a rejected PS-224 exemption used to
        # vanish without a word.
        from ._exemption_config_errors import report_exemption_config_errors

        report_exemption_config_errors(
            repo,
            config,
            _RULE,
            lambda where, detail: out.append(violation_cls(_RULE, where, detail)),
        )

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
    # UNCONDITIONAL FLOOR ∪ per-host state. scitex-dev owns the single
    # registry and SHIPS the canonical seed in its own code, so the seed is
    # always in play: per-host `hosts.yaml` is mutable and edited live, and
    # if it REPLACED the seed (the old fallback) then registering one
    # unrelated machine would hide `spartan` and turn every migrated job
    # red — the gate's verdict would move under repos that changed nothing.
    # Per-host state may EXTEND the floor, never subtract from it. This is
    # not a blanket pass: both sides are REAL measured destinations, and a
    # job neither side serves still errors below.
    floor = (
        packaged_default_runner_destinations()
        if floor_destinations is None
        else list(floor_destinations)
    )
    # Floor ∪ user-state is composed HERE, so the reader must NOT union the
    # shipped seed in as well — that would make the gap branch unreachable.
    user_state = list_runner_destinations(
        hosts_path=hosts_path, include_packaged_floor=False
    )
    destinations = _union_destinations(floor, user_state)
    if not destinations:
        # Only reachable when the shipped seed AND the user-state registry
        # BOTH carry no destinations — a code regression, not a deployment
        # state. Honest "could not check", never a green: a check that could
        # not run must not report what a check that passed reports.
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
                site = _site(rel, str(job_id))
                detail = _wx.delegated_exposure_detail(doc, job, job_id)
                if detail and not _exempt(site):
                    d = detail + _exempt_hint(site)
                    out.append(violation_cls(_RULE, site, d))
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

            # Match against the RESOLVED destinations (the shipped floor
            # UNIONed with user-state) — not a fresh `find_runner_host`,
            # which would read user-state ONLY and ignore the floor. Same
            # rule as `HostRecord.serves`: a runner serves the job when its
            # label set contains every requested label.
            wanted = frozenset(labels)
            # GitHub-hosted images are served by the platform, always, so they
            # cannot produce the unmatchable job this rule reports. Checked
            # BEFORE the registry so a hosted destination never depends on
            # local state — see GITHUB_HOSTED_LABELS.
            if _is_github_hosted(wanted):
                continue
            if any(wanted <= served for _host, served in destinations):
                continue

            if _exempt(site):
                continue

            exposed, events, secrets = _wx.is_exposed_credential_job(doc, job)
            out.append(
                violation_cls(
                    _RULE,
                    site,
                    _wx.destination_detail(
                        job_id, labels, registry_file, legal, exposed, events, secrets
                    )
                    + _exempt_hint(site),
                )
            )


# EOF
