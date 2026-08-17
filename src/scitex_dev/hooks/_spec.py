#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/hooks/_spec.py
"""The HookRule contract -- what a package DECLARES when it owns a guardrail.

This is the *agent* guardrail surface (Claude Code ``PreToolUse`` and friends),
NOT ``scitex_dev._hooks``, which is the private git-hook runner (pre-push,
lint, testmon) for scitex-dev's own repository. The two are unrelated; the
names are close because both are "hooks" in their own ecosystems.

A rule is DECLARED here and APPLIED elsewhere. The declaration carries the
identity, the policy and -- crucially -- the REASON, so the ruleset can be
read, reviewed and audited without reverse-engineering a pile of shell.

ONE RULE, MANY CONSUMERS
------------------------
A guardrail is usually enforced on more than one surface: a shell hook gates
``Bash``/``Edit``, while an in-process filter gates an MCP tool call. Those are
two BINDINGS of ONE rule, never two rules::

    HookRule(
        id="telegrammer.no-bare-issue-number",
        rule="Every #NNN in an operator-facing message must be followed by a "
             "parenthetical description.",
        reason="He reads on a phone, cannot follow a link, and the number "
               "alone says nothing about what changed.",
        event="pre-tool-use",
        severity="deny",
        matches=("mcp:claude-code-telegrammer.reply",),
        script="hooks/enforce_telegram_no_bare_issue.sh",
        predicate="hooks/_telegram_rules.py",
        provider="claude-code-telegrammer",
    )

``script`` and ``predicate`` are deliberately separate. ``script`` is the thin
shim the hook runner executes; ``predicate`` is the single implementation of
the matching logic, shipped ADJACENT to the shim and resolved by PATH relative
to it -- never by import. That distinction is load-bearing and was measured:
resolving the predicate via ``python -m scitex_dev...`` makes every hook
execution depend on ``scitex_dev`` being importable in whichever interpreter
the hook resolves to inside an agent container. The venv is per-agent and
apptainer overlays isolate it, so that import is not a fleet guarantee. A hook
that cannot load its rule must fail OPEN (you cannot block every message the
operator is waiting on because of a packaging slip) -- and fail-open plus a
non-guaranteed import is a gate that silently enforces nothing.

The predicate also OWNS THE REFUSAL WORDING. ``rule`` and ``reason`` make the
policy single-sourced, but if each binding formats its own refusal text the two
surfaces still drift on the one thing a human actually reads, and the wording
IS the fix instruction. Bindings render the predicate's message; they do not
compose their own.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Lifecycle points a rule may attach to. Mirrors the Claude Code hook events.
ALLOWED_EVENTS: tuple[str, ...] = (
    "pre-tool-use",
    "post-tool-use",
    "user-prompt-submit",
    "session-start",
    "stop",
    "notification",
)

#: What the rule DOES when it matches.
#:
#: ``deny``   -- refuses the action outright (the hook exits non-zero).
#: ``warn``   -- permits the action but emits a visible complaint.
#: ``advise`` -- permits silently-ish; guidance only, no obstruction.
ALLOWED_SEVERITIES: tuple[str, ...] = ("deny", "warn", "advise")


@dataclass(frozen=True)
class HookRule:
    """One declared agent guardrail, owned by exactly one package.

    Fields
    ------
    id
        Stable, unique, namespaced identifier -- ``"<owner>.<slug>"``, e.g.
        ``"sac.no-raw-apptainer-build"``. This is the dedup key and the handle
        an auditor skip refers to, so it must not change once published.
    rule
        ONE imperative sentence stating what is refused or required. Write it
        from what the implementation actually matches, not from what the
        filename implies.
    reason
        WHY the rule exists -- the incident, directive or doctrine behind it.
        This is the field that makes the corpus auditable rather than folkloric;
        a rule whose reason nobody can state is a rule nobody can retire.
    event
        One of :data:`ALLOWED_EVENTS`.
    severity
        One of :data:`ALLOWED_SEVERITIES`.
    matches
        The surfaces this rule gates. Tool names for native tools (``"Bash"``,
        ``"Edit"``) and ``"mcp:<server>.<tool>"`` for MCP calls. A rule
        enforced on both a shell surface and an MCP surface lists BOTH here --
        that is what makes it one rule with two consumers.
    provider
        The declaring package as a DISTRIBUTION name (e.g.
        ``"scitex-agent-container"``). A provider may leave this empty:
        discovery stamps it from the entry point's own distribution, exactly
        as it already does for ``owner_module`` below.

        It defaults to empty rather than being required BECAUSE it is a value
        discovery already knows. Making a leaf repeat it buys nothing and
        costs the one thing a repeated identity always costs — the chance to
        get it wrong. A plausible-but-incorrect ``provider`` does not raise;
        it misattributes the rule in every dedup and ownership path
        downstream, which is strictly worse than the TypeError that requiring
        it produced.
    owner_module
        The IMPORT anchor ``script`` and ``predicate`` resolve against (e.g.
        ``"scitex_agent_container"``). A provider may leave this empty:
        discovery stamps it from the entry point that supplied the rule, so a
        leaf does not have to repeat its own module name.

        This is the anchor half of the resolution contract. ``provider`` is a
        DISTRIBUTION name and cannot be imported; resolving a package-relative
        asset needs a MODULE. Given both, :func:`resolve_asset` locates the
        file through ``importlib.resources``, which is the only lookup that
        survives a zipped wheel.

        The rejected alternative was to have providers return absolute paths
        computed from ``__file__``. That needs no new field, but it bakes the
        building machine's filesystem into the declaration: two hosts would
        print different corpora for identical code, and
        ``dev hooks list-rules --json`` -- which the auditor and the operator both
        read -- would stop being comparable across machines.
    script
        Package-relative path to the shell binding, or ``None`` when the rule
        is enforced only in-process.
    predicate
        Package-relative path to the shared implementation that ships ADJACENT
        to ``script`` and is resolved relative to it at run time. Requires
        ``script``. ``None`` when the shim needs no separate predicate.
    check
        Dotted path (``"module:callable"``) for in-process consumers that can
        import it. Optional, and never the only binding a shell hook relies on.
    bypass
        The documented escape-hatch environment variable, if the rule has one
        (e.g. ``"CC_ALLOW_FOREGROUND_HEAVY"``). ``None`` when there is no way
        around it. Recording this is deliberate: an undocumented bypass is
        indistinguishable from a hole.
    implemented_in
        Where the implementation lives TODAY when the owning package does not
        yet ship it -- e.g.
        ``"dotfiles:src/.claude/to_claude/hooks/pre-tool-use/enforce_fd.sh"``.

        This field exists because the honest migration path is
        DECLARE-THEN-MOVE. Most of the fleet's guardrails are deployed from
        trees outside any Python package, and requiring a repo-relative
        ``script`` before they move would force every first declaration to
        name a file the package does not ship -- a dangling binding, which is
        exactly the defect PS-HOOK-011 exists to catch. A rule may therefore
        be declared with ``implemented_in`` alone: it becomes enumerable,
        reviewable and auditable immediately, and gains a real binding when
        the implementation lands in the package.
    doctrine
        Path or URL to the fuller explanation (a skill file, an ADR).
    """

    id: str
    rule: str
    reason: str
    event: str
    severity: str
    matches: tuple[str, ...]
    provider: str = ""
    owner_module: str = ""
    script: str | None = None
    predicate: str | None = None
    check: str | None = None
    bypass: str | None = None
    implemented_in: str = ""
    doctrine: str = ""

    def __post_init__(self) -> None:
        # Fail EARLY at construction so a malformed declaration never reaches
        # the aggregator, a report, or an installer -- exactly like
        # SystemDepSpec and JobSpec.
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError(f"HookRule.id must be a non-empty id; got {self.id!r}")
        if self.id != self.id.strip() or " " in self.id:
            raise ValueError(
                f"HookRule.id must not contain whitespace; got {self.id!r}"
            )
        if "." not in self.id:
            raise ValueError(
                f"HookRule({self.id!r}).id must be NAMESPACED as "
                f"'<owner>.<slug>' -- an unnamespaced id collides across "
                f"packages in a federated corpus."
            )
        if not isinstance(self.rule, str) or not self.rule.strip():
            raise ValueError(
                f"HookRule({self.id!r}).rule must state, in one sentence, what "
                f"is refused or required; got {self.rule!r}"
            )
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError(
                f"HookRule({self.id!r}).reason must say WHY the rule exists -- "
                f"an unexplained guardrail cannot be reviewed or retired."
            )
        if self.event not in ALLOWED_EVENTS:
            raise ValueError(
                f"HookRule({self.id!r}).event must be one of {ALLOWED_EVENTS}; "
                f"got {self.event!r}"
            )
        if self.severity not in ALLOWED_SEVERITIES:
            raise ValueError(
                f"HookRule({self.id!r}).severity must be one of "
                f"{ALLOWED_SEVERITIES}; got {self.severity!r}"
            )
        if not isinstance(self.matches, tuple) or not self.matches:
            raise ValueError(
                f"HookRule({self.id!r}).matches must be a non-empty tuple of "
                f"surfaces; got {self.matches!r}"
            )
        for surface in self.matches:
            if not isinstance(surface, str) or not surface.strip():
                raise ValueError(
                    f"HookRule({self.id!r}).matches entries must be non-empty "
                    f"surface names; got {surface!r}"
                )
        # EMPTY is legal at construction and means "discovery will stamp it"
        # (see the field docs). What stays illegal is a provider that is
        # present but not a string, or whitespace pretending to be a name —
        # those are declarations, and a wrong declaration misattributes the
        # rule silently, which is worse than the TypeError that requiring the
        # field produced. Leaf packages that construct HookRule directly do
        # not have to repeat an identity `_make_ep_provider` already knows.
        if not isinstance(self.provider, str) or (
            self.provider and not self.provider.strip()
        ):
            raise ValueError(
                f"HookRule({self.id!r}).provider must be the declaring "
                f"package's DISTRIBUTION name, or empty to let discovery "
                f"stamp it from the entry point; got {self.provider!r}"
            )
        if self.script is None and self.check is None and not self.implemented_in:
            raise ValueError(
                f"HookRule({self.id!r}) is untraceable -- set `script` "
                f"(shell binding), `check` (in-process binding), or at "
                f"minimum `implemented_in` naming where the implementation "
                f"lives today. A rule nobody can locate cannot be reviewed."
            )
        if self.predicate is not None and self.script is None:
            raise ValueError(
                f"HookRule({self.id!r}).predicate is resolved RELATIVE to "
                f"`script`, so it requires one. Use `check` for an "
                f"import-based binding instead."
            )

    @property
    def is_blocking(self) -> bool:
        """Whether a match refuses the action outright."""
        return self.severity == "deny"


def resolve_asset(rule: HookRule, which: str = "script"):
    """Locate a rule's ``script`` or ``predicate`` on disk, or return ``None``.

    Resolution goes through ``importlib.resources`` anchored at
    ``rule.owner_module`` -- the only lookup that also works when the owning
    package is installed as a zipped wheel.

    Returns ``None`` rather than raising when the rule declares no such asset,
    names no anchor, or the anchor cannot be imported: a caller listing the
    corpus must not blow up because one leaf is half-installed.
    """
    value = getattr(rule, which, None)
    if not value or not rule.owner_module:
        return None
    try:
        from importlib.resources import files
    except ImportError:  # pragma: no cover - Python < 3.9
        return None
    try:
        candidate = files(rule.owner_module).joinpath(value)
    except (ImportError, ModuleNotFoundError, TypeError):
        return None
    try:
        if not candidate.is_file():
            return None
    except OSError:  # pragma: no cover - exotic loaders
        return None
    return candidate


#: Provider callable shape leaves register under the entry-point group.
HookRuleProvider = "Callable[[], list[HookRule]]"

__all__ = [
    "ALLOWED_EVENTS",
    "ALLOWED_SEVERITIES",
    "HookRule",
    "HookRuleProvider",
    "resolve_asset",
]
