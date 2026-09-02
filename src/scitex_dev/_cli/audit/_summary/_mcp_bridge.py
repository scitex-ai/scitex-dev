"""§1 — MCP umbrella-bridge / mount-pattern discipline.

Extracted from `_mcp_audit.py` to keep the orchestrator under the
per-file line budget. Mirrors the existing §6 (`_mcp_parity.py`) and §2/§5
(`_mcp_tool_naming.py`) splits.

What lives here:
- ``_resolve_mcp_server(package)`` — locate the standalone `FastMCP`
  instance for a package.
- ``_default_import_bridge_pkg()`` / ``_read_bridge_source(package, *,
  import_bridge_pkg=None)`` — read the umbrella's
  `scitex/_mcp_tools/<short>.py` bridge source.
- ``_check_bridge_pattern(package, out, *, read_bridge_source=None,
  resolve_mcp_server=None)`` — §1 audit rule.
- ``BRIDGE_OWNER`` / ``bridge_violation(...)`` — who the finding is ABOUT.

Re-exported from `_mcp_audit` so existing call sites and test imports
keep working.

WHOSE DEFECT IS A BRIDGE FINDING?
---------------------------------
Every file this rule reads is ``scitex/_mcp_tools/<short>.py``, which
ships in the UMBRELLA distribution — never in the audited package's
repository. Until 2026-08-30 the finding was nonetheless emitted against
the audited package, at ``§1``/error, inside that package's REQUIRED
merge gate. In scitex-io's CI that read:

    [§1] scitex-io: umbrella bridge `scitex/_mcp_tools/io.py` uses
         direct `mcp.mount(...)`

scitex-io cannot fix that file. It is not in its tree, it does not
declare the umbrella as a dependency (the umbrella arrives
transitively), and it cannot pin it.

THE CONTROL THAT PROVES IT IS NOT A PROPERTY OF THE AUDITED PACKAGE:
scitex-io PR #167 resolved no ``scitex==`` at all and its CI headline
shows NO §1. Same repository, same rule, same code — the finding appears
or vanishes purely on whether the umbrella happened to be installed in
that job. A verdict that flips on an unrelated third party's presence
is a fact about the environment, not about the package being graded.
(For completeness: CI resolved ``scitex==2.28.13``, whose
``_mcp_tools/io.py`` still called raw ``mcp.mount()``. The umbrella
fixed it in 2.29.0 via ``safe_mount``. So the finding was true about the
umbrella and stale about io.)

The fix follows the grain the severity registry already has for §10/§10w
— a rule id is the ONLY carrier of severity, so a finding that must be
non-gating needs its own id:

* ``§1``  — the audited package OWNS the bridge (it *is* the umbrella).
            error-tier, gating, as before.
* ``§1u`` — the bridge belongs to ``scitex`` and someone else's audit
            merely imported it. Attributed to ``scitex`` (the
            ``Violation.command`` names the OWNER, so the printed line
            says whose file it is) and registered warn-tier, so it stays
            fully visible and reported without failing a gate its
            subject cannot pass.

WHAT THIS DOES NOT YET GIVE YOU — say it here rather than let a reader
infer it from the `§1` branch: the owner branch is REACHABLE BUT NOT
REACHED in production today, so §1 is currently warn-only in practice.
Two independent reasons, both pre-existing and neither introduced here:

  1. ``_mcp_audit._MCP_AUDIT_SKIP_PACKAGES`` contains ``scitex``, so
     ``audit-mcp-tools`` returns ``skip-not-standalone`` for the umbrella
     before any rule runs;
  2. even without that, ``_short_name("scitex")`` is ``"scitex"``, so the
     rule would look for ``scitex/_mcp_tools/scitex.py`` — the umbrella's
     bridges are per-sub-package (``io.py``, ``cloud.py``, …) and no such
     aggregate file exists.

Making §1 bite its owner therefore needs the umbrella's audit to SWEEP
its own bridge directory rather than look up one file by the audited
package's short name. That is a real gap and a separate change; it is not
closed by moving the blame, and pretending otherwise would trade a
misattributed gate for an imaginary one. The unit tests in
`tests/.../test__mcp_bridge.py` prove the owner branch grades correctly
when it is entered; they do not claim it is entered today.

NOT DONE ON PURPOSE: retargeting the rule at the umbrella's newer
``_mcp/`` package. From scitex 2.30.2 the umbrella ships NO per-package
bridge files there at all, so ``_read_bridge_source`` would return None
for EVERY package permanently — an ecosystem-wide silent disable that
looks green. `_check_workflow_duplication.py` names that shape: a
constant that is "a MEASUREMENT WITH AN EXPIRY DATE… a stale set fails
QUIETLY."
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

from ._audit import Violation
from ._mcp_names import _import_name, _short_name


def _resolve_mcp_server(package: str):
    """Locate a `FastMCP` instance for `package`.

    Tries module candidates `scitex_<pkg>._mcp_server`, `scitex_<pkg>.mcp_server`
    and looks for a top-level `mcp` attribute that is a `FastMCP`. Returns the
    instance or None.
    """
    try:
        from fastmcp import FastMCP  # local import to keep the module light
    except ImportError:
        return None

    import_name = _import_name(package)
    candidates = [
        f"{import_name}._mcp_server",
        f"{import_name}.mcp_server",
        f"{import_name}._mcp.server",  # scitex-io shape
        f"{import_name}.mcp.server",
    ]
    for mod_name in candidates:
        try:
            mod = importlib.import_module(mod_name)
        except BaseException:
            # `BaseException` (not just `Exception`) — some packages call
            # `sys.exit(1)` at module-import time when their preconditions
            # fail (e.g. scitex-orochi when telegram-bot env vars are unset).
            # SystemExit derives from BaseException, so a plain `except Exception`
            # would let it propagate and kill the audit run.
            continue
        for attr in ("mcp", "server", "app"):
            obj = getattr(mod, attr, None)
            if isinstance(obj, FastMCP):
                return obj
    return None


def _default_import_bridge_pkg():
    """Default bridge-pkg importer used by `_read_bridge_source`.

    Function-local import (lazy) so PA-304's module-level scan exempts it —
    auditing the umbrella's private bridge package by design is the one
    place where importing `scitex._mcp_tools` is intentional, not a
    violation.
    """
    import scitex._mcp_tools as bridge_pkg  # noqa: PA-304

    return bridge_pkg


def _read_bridge_source(
    package: str,
    *,
    import_bridge_pkg=None,
) -> str | None:
    """Read `scitex/_mcp_tools/<short>.py`; None if absent.

    The optional ``import_bridge_pkg`` callable lets tests inject a fake
    bridge module without monkey-patching — same convention as
    ``read_bridge_source`` / ``resolve_mcp_server`` on
    ``_check_bridge_pattern``.
    """
    if import_bridge_pkg is None:
        import_bridge_pkg = _default_import_bridge_pkg
    short = _short_name(package)
    try:
        bridge_pkg = import_bridge_pkg()
    except Exception:
        return None
    # `__file__` is None for namespace packages (no concrete __init__.py).
    # `getattr(obj, "__file__", "")` with a default of "" does NOT help here:
    # the attribute *exists* and *is None*, so the default never fires.
    # `Path(None)` then raises TypeError — which used to crash
    # `test_audit_all_clean` ecosystem-wide whenever the umbrella's
    # `_mcp_tools` resolved as a namespace pkg, forcing admin-merge on every
    # scitex-* PR. Treat a None `__file__` as "no concrete bridge file" —
    # semantically equivalent to a missing bridge, which the §1 rule
    # already handles silently (presence is checked by §6 parity).
    pkg_file = getattr(bridge_pkg, "__file__", None)
    if pkg_file is None:
        return None
    pkg_dir = Path(pkg_file).parent
    bridge = pkg_dir / f"{short}.py"
    if not bridge.is_file():
        return None
    try:
        return bridge.read_text(encoding="utf-8")
    except OSError:
        return None


_HAND_WRAP_DECORATOR = re.compile(r"@\s*mcp\s*\.\s*tool\s*\(")
_SAFE_MOUNT_CALL = re.compile(r"\bsafe_mount\s*\(")
_PLAIN_MOUNT_CALL = re.compile(r"\.\s*mount\s*\(")


#: The distribution that SHIPS every `scitex/_mcp_tools/<short>.py` file
#: this rule reads. Not a guess about layout: `_read_bridge_source`
#: literally imports `scitex._mcp_tools` and reads a sibling of its
#: `__file__`, so the owner of anything it returns is, by construction,
#: whatever distribution provides `scitex`.
BRIDGE_OWNER = "scitex"

#: Warn-tier sibling of §1, for a bridge finding raised during SOMEONE
#: ELSE'S audit. Same shape as §10w next to §10: severity is rule-keyed,
#: never per-finding, so "the same defect, but not gating for this
#: subject" can only be expressed as a second rule id.
BRIDGE_RULE_OWNED = "§1"
BRIDGE_RULE_THIRD_PARTY = "§1u"


def bridge_violation(package: str, defect: str, *, remedy: str) -> Violation:
    """One §1 bridge finding, attributed to whoever SHIPS the file.

    ``package`` is the package being AUDITED; the returned violation's
    ``command`` is the package that OWNS the bridge. Those are the same
    thing only when the umbrella audits itself — in every other run the
    audited package is a bystander that imported the umbrella, and
    naming it as the subject is how a third party's defect ended up
    inside its required merge gate.

    Returns an error-tier ``§1`` for the owner and a warn-tier ``§1u``
    for everyone else. The finding is never dropped, filtered or
    silenced in either case: it prints, it is counted in the warning
    tally, and it carries the owner's name and the remedy. Only the
    blame moves.
    """
    if package == BRIDGE_OWNER:
        return Violation(package, BRIDGE_RULE_OWNED, f"{defect} — {remedy}")
    return Violation(
        BRIDGE_OWNER,
        BRIDGE_RULE_THIRD_PARTY,
        f"{defect} — {remedy}. This file ships in `{BRIDGE_OWNER}`, not in "
        f"`{package}`; it surfaced here only because `{package}`'s audit "
        f"imported the installed umbrella. Fix it in the `{BRIDGE_OWNER}` "
        f"repository — `{package}` cannot: the file is not in its tree and "
        "it does not depend on the umbrella. Warn-tier for that reason: a "
        "package must not be gated on a file it does not ship.",
    )


def _check_bridge_pattern(
    package: str,
    out: list[Violation],
    *,
    read_bridge_source=None,
    resolve_mcp_server=None,
) -> None:
    """§1 — umbrella bridge must use `safe_mount` (or equivalent), not hand-wrap.

    Exempt when the standalone has no `<pkg>._mcp_server.mcp`: the bridge
    cannot `safe_mount` a non-existent server, so hand-wrapping is the
    only available option. The §1 rule only applies when the bridge
    *could* mount but chose not to.

    ``package`` is the package under audit; the finding itself is
    attributed by :func:`bridge_violation` to whoever ships the bridge —
    ``§1`` when they are the same, ``§1u`` (warn) against ``scitex``
    when they are not. See this module's docstring for why.

    The optional ``read_bridge_source`` / ``resolve_mcp_server`` callables
    let tests inject fakes without monkey-patching the module.
    """
    if read_bridge_source is None:
        read_bridge_source = _read_bridge_source
    if resolve_mcp_server is None:
        resolve_mcp_server = _resolve_mcp_server
    src = read_bridge_source(package)
    if src is None:
        # No bridge → not flagged here; presence is checked under §6 parity.
        return
    short = _short_name(package)
    has_safe_mount = bool(_SAFE_MOUNT_CALL.search(src))
    has_plain_mount = bool(_PLAIN_MOUNT_CALL.search(src))
    has_hand_wrap = bool(_HAND_WRAP_DECORATOR.search(src))

    if has_hand_wrap and not (has_safe_mount or has_plain_mount):
        # Standalone-side check: if `<pkg>._mcp_server.mcp` doesn't
        # resolve, hand-wrap is the only option. Don't penalise the
        # standalone for the umbrella's choice when no alternative exists.
        if resolve_mcp_server(package) is None:
            return
        out.append(
            bridge_violation(
                package,
                f"umbrella bridge `scitex/_mcp_tools/{short}.py` "
                "hand-wraps tools",
                remedy="convert to `safe_mount(mcp, sub_mcp, namespace=…)` "
                "(see scitex/_mcp_tools/cloud.py)",
            )
        )
        return  # don't double-report

    if has_plain_mount and not has_safe_mount:
        out.append(
            bridge_violation(
                package,
                f"umbrella bridge `scitex/_mcp_tools/{short}.py` "
                "uses direct `mcp.mount(...)`",
                remedy="replace with `safe_mount(mcp, sub_mcp)` from "
                "`scitex._mcp_tools._compat` for FastMCP 2.x/3.x portability",
            )
        )
