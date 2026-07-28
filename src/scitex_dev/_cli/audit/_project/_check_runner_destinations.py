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
  (constitution §2) — an exemption must state WHY.

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

Supported ``runs-on`` forms
---------------------------
::

    runs-on: ubuntu-latest                              # bare string
    runs-on: [self-hosted, Linux, X64, scitex-ci]       # list
    runs-on: {labels: [self-hosted, scitex-ci]}         # mapping
    runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '["self-hosted","Linux","X64","scitex-ci"]') }}

The last is the fleet idiom; the LITERAL FALLBACK inside the expression
is what gets validated. That fallback is what actually runs whenever the
``CI_RUNS_ON`` repo/org variable is unset, which is the common case — so
validating it is validating the real destination, not a decoration.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

#: A ``${{ ... }}`` expression block (contents captured).
_RE_EXPR_BLOCK = re.compile(r"\$\{\{\s*(.+?)\s*\}\}", re.DOTALL)

#: ``fromJSON( ... )`` — the scitex CI idiom; args captured for default mining.
_RE_FROMJSON = re.compile(r"fromJSON\s*\((.*)\)", re.IGNORECASE | re.DOTALL)

#: A single-level JSON array literal, e.g. ``["self-hosted","Linux"]``.
_RE_JSON_ARRAY = re.compile(r"(\[[^\[\]]*\])")

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
            "serves the label set. Exempt a single site only via "
            "`audit.exemptions` with a stated reason (constitution §2)."
        ),
        "E",
        "runner-destination-unregistered",
    ),
]


def _as_labels(value: Any) -> list[str]:
    """Flatten a raw ``runs-on`` value into its label strings.

    Handles the scalar, sequence and ``labels:``/``group:`` mapping forms.
    Returns the labels VERBATIM — expression resolution happens later, in
    :func:`_resolve_destination`.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, (str, int, float))]
    if isinstance(value, dict):
        out: list[str] = []
        for key in ("labels", "group"):
            got = value.get(key)
            if isinstance(got, str):
                out.append(got)
            elif isinstance(got, list):
                out.extend(str(v) for v in got if isinstance(v, str))
        return out
    return []


def _fromjson_literal(args: str) -> list[str] | None:
    """Resolve ``fromJSON(... || '<json-array>')`` to its literal fallback.

    Returns the FIRST JSON-array literal in the ``fromJSON`` arguments —
    the fleet idiom's ``|| '[...]'`` default, or a direct
    ``fromJSON('[...]')``. ``None`` when there is no array literal to read,
    which makes the destination unresolvable.
    """
    for match in _RE_JSON_ARRAY.finditer(args):
        try:
            parsed = json.loads(match.group(1))
        except ValueError:
            continue
        if isinstance(parsed, list):
            return [str(x) for x in parsed if isinstance(x, str)]
    return None


def _resolve_destination(runs_on: Any) -> list[str] | None:
    """Resolve one ``runs-on`` to the concrete label set it requests.

    Returns ``None`` when the destination is NOT statically resolvable —
    an expression carrying no literal to read. The caller reports that as
    a violation in its own right (the workflow does not name its
    destination explicitly), never as a silent pass.
    """
    raw_labels = _as_labels(runs_on)
    if not raw_labels:
        return None
    resolved: list[str] = []
    for label in raw_labels:
        block = _RE_EXPR_BLOCK.search(label)
        if block is None:
            resolved.append(label.strip())
            continue
        from_json = _RE_FROMJSON.search(block.group(1))
        if from_json is None:
            return None
        literal = _fromjson_literal(from_json.group(1))
        if literal is None:
            return None
        resolved.extend(x.strip() for x in literal)
    concrete = [label for label in resolved if label]
    return concrete or None


def _workflow_files(repo: Path) -> list[Path]:
    """Every ``.github/workflows/*.y{a,}ml`` file, sorted.

    ``.github`` is a HIDDEN directory: a walker that skips dotted dirs
    returns zero matches here, which is indistinguishable from "this repo
    has no workflows". The path is therefore built explicitly, never
    discovered by a recursive scan.
    """
    wf_dir = repo / ".github" / "workflows"
    if not wf_dir.is_dir():
        return []
    return sorted(
        path
        for path in wf_dir.iterdir()
        if path.is_file() and path.suffix in {".yml", ".yaml"}
    )


def _describe(destinations: list[tuple[str, frozenset[str]]]) -> str:
    """Render the registry's legal destinations for a violation message."""
    return "; ".join(
        f"{host}: [{', '.join(sorted(labels))}]" for host, labels in destinations
    )


def check_ps224_runner_destinations(
    repo: Path,
    violation_cls: type,
    out: list,
    *,
    hosts_path: str | Path | None = None,
    floor_destinations: list[tuple[str, frozenset[str]]] | None = None,
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
    """
    workflows = _workflow_files(repo)
    if not workflows:
        return

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
        rel = str(path.relative_to(repo))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
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
            runs_on = job["runs-on"]
            labels = _resolve_destination(runs_on)

            if labels is None:
                out.append(
                    violation_cls(
                        _RULE,
                        rel,
                        f"job `{job_id}` does not name its runner destination "
                        f"explicitly: `runs-on: {runs_on}` has no statically "
                        "readable label set. Every workflow must name a "
                        "destination the machine registry can be checked "
                        "against — otherwise a variable is a universal "
                        "bypass. Use a literal label list, or the fleet idiom "
                        "whose `|| '[...]'` fallback IS the literal: "
                        "`runs-on: ${{ fromJSON(vars.CI_RUNS_ON || "
                        "'[\"self-hosted\",\"Linux\",\"X64\",\"scitex-ci\"]') "
                        f"}}`. Registered destinations: {legal}.",
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

            out.append(
                violation_cls(
                    _RULE,
                    rel,
                    f"job `{job_id}` targets `[{', '.join(labels)}]`, which NO "
                    f"registered machine serves (registry: {registry_file}). "
                    "GitHub does not reject an unmatchable job — it queues it "
                    "forever, so this never fails, it just never runs. Point "
                    "the job at a registered destination, or register the "
                    "machine that serves this label set in the registry's "
                    f"`runner_labels:`. Registered destinations: {legal}.",
                )
            )


# EOF
