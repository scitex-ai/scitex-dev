"""Literal-constant checks (STX-NL001 / STX-HPC001) for ``SciTeXChecker``.

Mixed into :class:`scitex_dev.linter.checker.SciTeXChecker`; uses its
``source_lines`` and ``_add``.
"""

import ast

from .. import rules
from .._source_helpers import _is_allowed_by_comment

__all__ = ["LiteralChecksMixin"]


class LiteralChecksMixin:
    """``visit_Constant``: integer separators and HPC ssh-multiplexing."""

    def visit_Constant(self, node: ast.Constant) -> None:
        """Flag integer literals ≥ 1_000 written without `_` separators
        (STX-NL001 / PEP 515 — see
        `_skills/general/03_interface/01_python-api/14_numeric-literals.md`).

        Carve-outs:
        - bool / float / complex / str / bytes / None — skipped.
        - abs(value) < 1000 — under threshold.
        - source segment already contains `_` — already conformant.
        - source segment is non-decimal (`0x…`, `0o…`, `0b…`) — left
          alone; the PEP applies but the rule keeps its scope narrow.
        - `# noqa: STX-NL001` on the line — explicit suppression for
          identifiers that read as a whole (years, ports, codes).
        """
        # STX-HPC001 — SSH multiplexing disabled on the HPC path: a string
        # literal that turns off the ssh control-master / control-path opens a
        # fresh login-node connection per call (Spartan admin incident
        # 2026-06-17: 440+ connections). The match tokens are split (`"=" + "no"`)
        # so this detector's OWN source does not trip the rule.
        _hpc_nomux = ("ControlMaster=" + "no", "ControlPath=" + "none")
        if isinstance(node.value, str) and any(t in node.value for t in _hpc_nomux):
            hpc_line = (
                self.source_lines[node.lineno - 1]
                if node.lineno - 1 < len(self.source_lines)
                else ""
            )
            if not _is_allowed_by_comment(hpc_line, "STX-HPC001"):
                self._add(rules.HPC001, node.lineno, node.col_offset, hpc_line)

        # Only int literals; explicitly reject bool (`True is 1`).
        if not isinstance(node.value, int) or isinstance(node.value, bool):
            self.generic_visit(node)
            return
        if abs(node.value) < 1000:
            self.generic_visit(node)
            return
        # Need the original source segment to see if `_` was used —
        # `node.value` normalises `21_600` and `21600` to the same int.
        src = ast.get_source_segment("\n".join(self.source_lines), node)
        if src is None or "_" in src:
            self.generic_visit(node)
            return
        if src.startswith(("0x", "0o", "0b", "0X", "0O", "0B")):
            # Non-decimal — same PEP applies but the rule keeps its
            # scope narrow to base-10 quantities for now.
            self.generic_visit(node)
            return
        line = (
            self.source_lines[node.lineno - 1]
            if node.lineno - 1 < len(self.source_lines)
            else ""
        )
        if _is_allowed_by_comment(line, "STX-NL001"):
            self.generic_visit(node)
            return
        self._add(rules.NL001, node.lineno, node.col_offset, line)
        self.generic_visit(node)


# EOF
