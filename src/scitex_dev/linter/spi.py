"""Public re-export surface for the SciTeX linter's internal building blocks.

Promotes three long-standing internal helpers — ``Rule``, ``FMChecker``, and
``_is_allowed_by_comment`` — to a stable public import path so peer packages
(and internal callers) can depend on ``scitex_dev.linter.spi`` instead of
reaching into ``scitex_dev.linter._rules._base`` / ``_fm_checker`` /
``checker`` directly.

"spi" = Service Provider Interface: the surface a THIRD PARTY plugs into to
extend the linter (custom rules via the ``Rule`` dataclass, custom
FM-style AST visitors via ``FMChecker``, custom suppression-comment
handling via ``_is_allowed_by_comment``) — as opposed to the linter's own
internal implementation modules.

This is a PROMOTION, not a move: the original private paths keep working
unchanged —

    scitex_dev.linter._rules._base.Rule
    scitex_dev.linter._fm_checker.FMChecker
    scitex_dev.linter.checker._is_allowed_by_comment

See ``docs/adr/0003-ecosystem-boundary-ports-and-producers.md`` and
``_skills/general/01_ecosystem/16_boundary-ports-and-producers.md`` — this
module is the "import the peer's public surface instead" fix pattern for
the a2 boundary smell those documents describe.
"""

from __future__ import annotations

from ._fm_checker import FMChecker
from ._rules._base import Rule
from .checker import _is_allowed_by_comment

__all__ = ["Rule", "FMChecker", "_is_allowed_by_comment"]
