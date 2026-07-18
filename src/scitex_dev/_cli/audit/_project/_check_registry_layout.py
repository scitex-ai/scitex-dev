"""PS-181 — ``~/.scitex/<pkg>/`` registry-layout conformance.

Unlike every sibling ``_check_*`` module in this package, this rule is
NOT repo-scoped: it does not take a single git checkout's ``Path`` and
look for drift inside that repo. Instead it inspects the user's entire
``$SCITEX_DIR`` tree (default ``~/.scitex``) — the local-state directory
of EVERY installed SciTeX package, cutting across whichever single
distribution `audit-project`/`audit-all` happen to be auditing right
now.

Wiring note (read before assuming this hooks into `audit-project`)
--------------------------------------------------------------------
`audit_project(distribution, repo=...)` and `run_audit_all(...)` in
`_summary/_audit.py` are fundamentally per-repo/per-distribution: every
existing check function takes a single repo root and every finding is
attributed to that one distribution. Folding a global, cross-package
rule into that per-repo loop would mean re-scanning the SAME
`~/.scitex/` tree once per audited package (wasteful and semantically
wrong — the drift has nothing to do with any one repo), and threading a
new "global" concept through `run_audit_all`'s tested JSON/human output
shape risked exactly the invasive refactor the task spec warned
against.

Instead, PS-181 is surfaced through a small, additive sibling entry
point: `scitex-dev ecosystem audit-registry-layout` (see
`_cli/ecosystem/_cmds/_audit_registry_layout.py`), which reuses the same
`RULES` / `Violation` formatting machinery as `audit-project` for
consistent output, but is invoked once for the whole `$SCITEX_DIR` tree
rather than once per distribution. `check_registry_layout()` below is
the pure function that command calls; it is exported here so it can
also be unit-tested standalone (mirrors sibling `_check_*` modules'
``(scope, violation_cls, out)`` signature, with the repo-`Path` swapped
for a `$SCITEX_DIR`-`Path`).

See the PR description for the 2-3 alternatives considered for wiring
this more deeply into `audit-all` (e.g. a `--include-registry-layout`
flag on `audit-all` appending one synthetic "package" record) if a
future task wants tighter integration.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev.registry_normalize.scan import scan_registry


def check_registry_layout(scitex_dir: Path, violation_cls: type, out: list) -> None:
    """Append PS-181 violations for every registry-layout drift instance
    found under *scitex_dir* (``$SCITEX_DIR`` root, default ``~/.scitex``).

    One ``violation_cls("PS-181", where, detail)`` per (pkg, drift
    instance) — mirrors the one-violation-per-offending-path convention
    used by ``check_runtime_separation`` (PS-180) and ``_check_license``
    (PS-138/PS-138b).
    """
    findings = scan_registry(scitex_dir)
    for _pkg, items in findings.items():
        for item in items:
            out.append(violation_cls("PS-181", item.path, item.detail))


# EOF
