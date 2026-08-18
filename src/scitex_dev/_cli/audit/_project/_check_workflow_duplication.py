#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PS-231 — a leaf workflow that RE-IMPLEMENTS an org-provided reusable one.

Operator ruling, 2026-08-15, to scitex-cards and then to me directly::

    cla must be handled via the shared workflow which is set for the
    organization, scitex-ai
    you must not re-invent that
    github workflows must follow the organizations ones unless leaf
    package's version is really unique to the leaf
    so if you failed cla, you must check if all the other leafs fail or not

    we must stop allowing duplicate workflows written in leaf packages

"Stop ALLOWING" is why this is a rule and not a cleanup ticket. A one-time
sweep leaves nothing behind that prevents the fifty-fourth copy.

WHAT IT COSTS TO HAVE TWO — measured, on this repo, today
----------------------------------------------------------
``scitex-dev``'s own ``pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml`` carried::

    runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '["self-hosted",...,"scitex-ci"]') }}

``scitex-ci`` is served by no online org runner. The org's ``pytest-matrix``
had the same defect and it was fixed there this morning — every CALLER picked
the fix up for free, and every LOCAL COPY did not. That is the whole argument
in one file: a duplicate does not merely cost maintenance, it silently opts out
of fixes, and it opts out in the direction where GitHub QUEUES the job forever
rather than rejecting it.

53 such files exist across 15 repositories as of 2026-08-15.

DETECTION IS BY NAME, AND THAT IS STATED RATHER THAN HIDDEN
------------------------------------------------------------
Two forms, both keyed on the filename stem:

* EXACT — ``cla.yml`` beside the org's ``cla``;
* RENAMED — ``pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml``, the fleet's
  ``<what>-on-<where>`` convention, beside the org's ``pytest-matrix``.

A structural comparison would be stronger and is not available: a leaf copy
drifts, so "does this file do what the org file does" has no cheap true answer.
The naming convention is a real fleet convention and the rule leans on it
openly, so a false positive is legible ("it is named like the org's and it is
not one") and answerable by an exemption.

WHAT IS NOT A DUPLICATE
------------------------
* A workflow that CALLS the org (``uses: scitex-ai/.github/...``). That is the
  target state, and it may be named anything.
* A workflow that DECLARES ``on: workflow_call``. That is a reusable
  definition, not a copy of one — which is how the ``scitex-ai/.github``
  checkout itself passes this rule without being special-cased by name. A
  name-based self-exemption would have been a lie that stopped working the
  moment the org repo was checked out under a different directory.

SEVERITY E, NO GRANDFATHERING — the operator already ruled on this shape
------------------------------------------------------------------------
Settled for the sibling PS-224 and quoted here so it is not relitigated:

* 「昔だろうが今だろうが問題点は問題点」 — an old problem is a problem. A
  new-vs-old ratchet is also structurally broken: the baseline runs the CURRENT
  rules against the OLD tree, so every hit of a NEWLY ADDED rule classifies as
  pre-existing and the rule is suppressed forever.
* 「全て赤でいいと思います。正直に赤から始めて、レッドスタート」 — a
  fleet-wide red is the INTENDED outcome. Red is the honest measurement; the
  list is then burned down.

I proposed grandfathering the 53 anyway and withdrew it on finding this ruling.

THE EXEMPTION IS THE OPERATOR'S OWN CAVEAT, MADE MECHANICAL
------------------------------------------------------------
He said "unless leaf package's version is really unique to the leaf". That is
exactly one reasoned exemption per workflow in ``.scitex/dev/config.yaml``
under ``audit.exemptions``, keyed on the workflow path, with a stated reason —
constitution §2. A blanket flag would erase the caveat's only interesting word,
which is "unless".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

_RULE = "PS-231"

#: An exemption site here is a FILE, not a line — the duplicate is the whole
#: workflow. Spelled locally, as the three sibling checks do, rather than
#: shared: a common constant would invite a shared "site" convention across
#: rules whose sites are genuinely different shapes (PS-224's is job-qualified,
#: PS-221's is a pyproject line).
_NO_LINE = 0

#: The reusable workflows `scitex-ai/.github` provides.
#:
#: MEASURED 2026-08-15 from the live repository, not from memory:
#:
#:     gh api repos/scitex-ai/.github/contents/.github/workflows --jq '.[].name'
#:     # then, per file, keep only those declaring `on: workflow_call`
#:
#: THE SECOND STEP IS NOT OPTIONAL, and leaving it out is how this list was
#: wrong on its first draft. The directory holds EIGHT files and only SEVEN are
#: callable: `self-test` is the org's own harness for its reusable workflows and
#: declares no `workflow_call` at all. Listing it would have produced a finding
#: whose remedy — "call it instead" — is impossible to follow, which is a worse
#: failure than not flagging: it sends someone to do a thing that cannot work.
#:
#: This is a MEASUREMENT WITH AN EXPIRY DATE, on the same terms as
#: `CI_RUNS_ON_DEFAULT` and the runner-destination floor. When the org adds or
#: retires a reusable workflow this set is stale, and a stale set fails QUIETLY
#: — a newly-provided workflow that is missing here means every leaf copy of it
#: goes unflagged, which reads as "no duplicates" rather than as "not checked".
#: Re-run the two steps rather than trusting this list.
ORG_REUSABLE_WORKFLOWS: frozenset[str] = frozenset(
    {
        "auto-merge-to-develop",
        "cla",
        "import-smoke",
        "promote-develop-to-main-on-tag",
        "pytest-matrix",
        "quality-audit",
        "rtd-sphinx-build",
    }
)

#: How many org-named reusable DEFINITIONS make a repo the PROVIDER.
#:
#: Two, because one is a leaf that happens to have factored its own reusable
#: workflow and named it like an org one; several is the org repo itself.
_PROVIDER_THRESHOLD = 2

#: A caller names the org repo here. Matching the OWNER/REPO rather than a full
#: ref so a caller pinned to a tag, a branch or a SHA all count as callers.
_CALLS_ORG = "scitex-ai/.github"

#: A reusable DEFINITION declares this. See "What is not a duplicate".
_DEFINES_REUSABLE = "workflow_call"

#: BOTH MARKERS ARE MATCHED IN POSITION, NEVER AS BARE SUBSTRINGS, and the
#: reason is a measured false negative rather than a style preference.
#:
#: The first draft tested `"scitex-ai/.github" in text`. Run against the fleet
#: it cleared `sac`'s `import-smoke-on-ubuntu-py3-12.yml` and
#: `rtd-sphinx-build-on-ubuntu-latest.yml` — two genuine local copies whose only
#: mention of the org is a COMMENT explaining why they do not call the reusable:
#:
#:     # (scitex-ai/.github/.github/workflows/import-smoke.yml). That reusable
#:     # stops ...
#:
#: So the check exempted the files for DOCUMENTING their own duplication, and
#: the better-documented a divergence was, the more certainly it went unflagged.
#: It fails in the direction that reads as clean, which is the direction nobody
#: re-checks. Found by diffing the rule's output against an independent
#: line-based census and refusing to wave away a four-file gap.
_USES_PREFIXES = ("uses:", "- uses:")


def _has_marker(text: str, marker: str, prefixes: tuple[str, ...]) -> bool:
    """True iff ``marker`` appears on a line that OPENS with one of ``prefixes``.

    Comment lines start with ``#``, so they never match — which is the whole
    point. A crude parse, deliberately: a real YAML load would raise on the
    malformed workflows this rule most wants an answer about, and "cannot
    parse" must not become "not a duplicate".
    """
    for line in text.splitlines():
        stripped = line.strip()
        if marker not in stripped:
            continue
        if any(stripped.startswith(prefix) for prefix in prefixes):
            return True
    return False

_WORKFLOW_SUFFIXES = (".yml", ".yaml")


def duplicated_org_workflow(stem: str) -> str | None:
    """Return the org workflow ``stem`` duplicates, or ``None``.

    ``<org>-on-<anything>`` counts because it is the fleet's own naming
    convention for "the org's X, run on Y" — and a leaf that renamed the file
    while copying its contents has duplicated it more thoroughly, not less.
    """
    if stem in ORG_REUSABLE_WORKFLOWS:
        return stem
    for org in sorted(ORG_REUSABLE_WORKFLOWS):
        if stem.startswith(f"{org}-on-"):
            return org
    return None


def iter_workflow_files(repo: Path) -> Iterable[Path]:
    """Yield the repo's workflow files, in a stable order.

    Sorted so a multi-finding report reads the same on every run — an unstable
    order turns a re-run into a diff and hides whether anything changed.
    """
    workflows = repo / ".github" / "workflows"
    if not workflows.is_dir():
        return []
    return sorted(
        path
        for path in workflows.iterdir()
        if path.is_file() and path.suffix in _WORKFLOW_SUFFIXES
    )


def calls_org(text: str) -> bool:
    """True iff the workflow actually CALLS an org reusable workflow."""
    return _has_marker(text, _CALLS_ORG, _USES_PREFIXES)


def defines_reusable(text: str) -> bool:
    """True iff the workflow DECLARES itself reusable (``on: workflow_call``)."""
    return _has_marker(text, _DEFINES_REUSABLE, (f"{_DEFINES_REUSABLE}:",))


def is_duplicate(text: str, stem: str) -> str | None:
    """Return the org workflow this file duplicates, or ``None``.

    Order matters: the two exemptions are checked BEFORE the name, so a caller
    or a reusable definition can be named anything without tripping the rule.
    """
    if calls_org(text):
        return None
    if defines_reusable(text):
        return None
    return duplicated_org_workflow(stem)


def _exempt_predicate(repo: Path, Violation: type, out: list[Any]):
    """Return ``site -> bool``, honouring only ACCEPTED (reasoned) exemptions.

    Same construction as PS-224: a reasonless entry never matches, and the
    shared config-error arm reports it at ``E`` — so an exemption with no
    stated reason suppresses nothing AND is itself a finding. That is what
    keeps "unless the leaf's version is unique" a claim someone has to make in
    writing rather than a flag.
    """
    try:
        from .._config import load_config

        config = load_config(repo)
    except Exception:  # noqa: BLE001 - a missing or malformed config must not
        # crash the audit. It must not silently disable the rule either: with
        # no config there are no accepted exemptions, so every duplicate is
        # still reported. Failing closed is the only safe direction here.
        config = None

    if config is not None:
        from ._exemption_config_errors import report_exemption_config_errors

        report_exemption_config_errors(
            repo,
            config,
            _RULE,
            lambda where, detail: out.append(Violation(_RULE, where, detail)),
        )

    exemption_for = getattr(config, "exemption_for", None)

    def _exempt(site: str) -> bool:
        if exemption_for is None:
            return False
        return bool(exemption_for(_RULE, site, _NO_LINE))

    return _exempt


def provides_org_workflows(repo: Path) -> bool:
    """True when this repo IS the provider of the org's reusable workflows.

    STRUCTURAL, NOT NAME-BASED, and that is the point. The obvious test —
    "is this repo called `.github`?" — fails immediately: the org repository is
    checked out locally as `scitex-org-github`, so a name test would flag the
    very repo whose workflows the rule defends.

    Counting definitions instead survives any directory name, any fork and any
    rename. The `self-test` case is why a per-file check alone is not enough:
    the org's own harness declares no `workflow_call`, so nothing about that
    FILE says "provider" — only the seven files beside it do.
    """
    definitions = 0
    for path in iter_workflow_files(repo):
        if path.stem not in ORG_REUSABLE_WORKFLOWS:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if defines_reusable(text):
            definitions += 1
            if definitions >= _PROVIDER_THRESHOLD:
                return True
    return False


def check_ps231_workflow_duplication(
    repo: Path, Violation: type, out: list[Any]
) -> None:
    """Flag every leaf workflow that re-implements an org-provided one."""
    if provides_org_workflows(repo):
        return
    exempt = _exempt_predicate(repo, Violation, out)
    for path in iter_workflow_files(repo):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            # An unreadable workflow is NOT silently passed. It cannot be
            # judged, and "cannot judge" must never render as "clean".
            out.append(
                Violation(
                    _RULE,
                    str(path),
                    (
                        "workflow file could not be read, so it could not be "
                        "checked for duplication of an org-provided reusable "
                        "workflow — an unreadable file is not a clean one"
                    ),
                )
            )
            continue
        org = is_duplicate(text, path.stem)
        if org is None:
            continue
        # Site is the repo-relative workflow path, so an exemption names the
        # ONE file it excuses. A repo-wide or rule-wide key is deliberately
        # not supported: the operator's caveat was about a leaf's version of a
        # PARTICULAR workflow being unique, and a broader key would excuse the
        # copies nobody looked at along with the one somebody justified.
        if exempt(str(path.relative_to(repo))):
            continue
        out.append(
            Violation(
                _RULE,
                str(path),
                (
                    f"re-implements the org-provided reusable workflow "
                    f"`{org}` instead of calling it. Replace the body with a "
                    f"caller — `uses: scitex-ai/.github/.github/workflows/"
                    f"{org}.yml@main` — or, if this package's version is "
                    "genuinely unique to the leaf, record a reasoned "
                    "exemption for this path under `audit.exemptions`. A "
                    "local copy does not track fixes made to the org "
                    "workflow: the `scitex-ci` runner-label defect was fixed "
                    "org-side on 2026-08-15 and every copy kept it. "
                    "NOTE, once converted: a caller has no local `runs-on:`, "
                    "so a hosted-runner allowlist entry for this path may "
                    "start to look unnecessary. IT IS NOT. The runner choice "
                    "moved upstream into the reusable; it did not disappear. "
                    "Do NOT delete such an entry as part of this conversion "
                    "— on at least one workflow that entry is the security "
                    "argument, not bookkeeping. Pass `runs_on` explicitly in "
                    "the caller so the decision stays locally visible. "
                    "BLOCKER 1 — REQUIRED STATUS CONTEXTS. Converting a job "
                    "into a caller RENAMES its published check context from "
                    "`<job>` to `<caller-job> / <callee-job>`, and the "
                    "separator is structural: no caller job name and no "
                    "callee input can produce a context without it. So if "
                    "the job you are converting publishes a context that "
                    "branch protection REQUIRES, the conversion is not a "
                    "workflow-only change — it is blocked on a protection "
                    "edit that must land with it, or every PR waits forever "
                    "on a check nothing can publish again. List the required "
                    "contexts first; if yours is among them, take the "
                    "exemption or get the protection edit, do not open a "
                    "workflow-only PR. ENUMERATE THEM PER PROTECTED "
                    "BRANCH, not once: develop and main can require "
                    "different contexts, and a sweep that converts "
                    "both locks both. AND THIS RULE CANNOT CHECK IT "
                    "FOR YOU — required contexts live in branch "
                    "protection, behind a different API, invisible to "
                    "every code-level check here. Measured 2026-08-18: "
                    "`audit` is REQUIRED on figrecipe and NOT required "
                    "on scitex-app, from workflow files that look "
                    "identical — so no linter and no reading of "
                    "`.github/workflows` can tell you whether your "
                    "conversion is safe. Run `gh api repos/{owner}/"
                    "{repo}/branches/{branch}/protection` for EACH "
                    "protected branch. A third failure mode looks "
                    "different and costs more: a converted caller that "
                    "PUBLISHES but can never succeed (measured on "
                    "scitex-app — a dependency-group mismatch made "
                    "every leg exit 4). That shows as an ORDINARY RED, "
                    "indistinguishable from a real test failure, so if "
                    "a conversion goes red suspect the conversion "
                    "before your tests. (Measured by figrecipe, 2026-08-18: "
                    "`audit` required on both develop and main, and the org "
                    "callee hard-codes `name: audit`, so `audit / audit` is "
                    "the best any caller can publish.) "
                    "BLOCKER 2 — A LEAF THAT ALSO PUBLISHES. If the leaf "
                    "vendors its build output back into the package tree "
                    "(grep it for a step committing `_sphinx_html`), the org "
                    "reusable is BUILD-ONLY and cannot replace it: hatch "
                    "packages `src/<pkg>` wholesale, so that bundle SHIPS "
                    "INSIDE THE WHEEL. A bare `uses:` keeps building and "
                    "stops publishing — green CI, frozen documentation "
                    "reaching users, nothing anywhere saying so. Check the "
                    "PR gate too: leaves that run `sphinx-build -W` lose it, "
                    "because the org build does not."
                ),
            )
        )


#: Co-located rule declaration, on the same terms as RUNNER_DESTINATION_RULES.
#: Severity **E** lives in the tuple, NOT in `_SEVERITY_OVERRIDES` — an
#: override for a co-located rule is a silent no-op, and a rule that ships at E
#: precisely so it CAN fail a build must not have its severity routed through a
#: table that would drop it.
WORKFLOW_DUPLICATION_RULES: list[tuple[str, str, str, str, str]] = [
    (
        _RULE,
        "§1",
        (
            "A leaf `.github/workflows/` file RE-IMPLEMENTS a reusable "
            "workflow that `scitex-ai/.github` already provides, instead of "
            "calling it. Operator ruling 2026-08-15: `github workflows must "
            "follow the organizations ones unless leaf package's version is "
            "really unique to the leaf` — and `we must stop allowing "
            "duplicate workflows written in leaf packages`. The cost is not "
            "maintenance: a copy silently opts OUT of fixes made org-side, "
            "and it does so in the direction where a job is queued forever "
            "rather than rejected. Measured 2026-08-15: 53 such files across "
            "15 repositories, all carrying a runner-label defect that had "
            "already been fixed in the org workflow that morning. A workflow "
            "that calls the org, or that declares `on: workflow_call`, is "
            "never flagged. Genuine leaf-specific variants take a reasoned "
            "per-path exemption under `audit.exemptions`."
        ),
        "E",
        "workflow-duplication",
    ),
]


# EOF
