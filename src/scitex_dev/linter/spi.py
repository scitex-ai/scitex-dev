"""Public re-export surface for the SciTeX linter's internal building blocks.

Promotes the long-standing helpers — ``Rule``, ``Issue``, ``FMChecker``, and
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

Rule scopes (``Rule.scope``) are part of this surface: a plugin rule
declaring ``scope=SCOPE_RESEARCH_SCRIPT`` is filtered by the ENGINE — for
call rules and plugin checkers alike — so it fires only in research scripts
(``is_research_script``). Plugins declare coverage the engine may require
for a project type via the payload key ``capabilities`` (e.g. scitex-io's
``"raw-io"``; see ``REQUIRED_CAPABILITIES``).
"""

from __future__ import annotations

from ._fm_checker import FMChecker
from ._issue import Issue
from ._provider_replacements import ProviderReplacement
from ._research_scope import (
    REQUIRED_CAPABILITIES,
    is_research_script,
    is_test_file,
)
from ._rules._base import SCOPE_ANY, SCOPE_RESEARCH_SCRIPT, SCOPES, Rule
from ._source_helpers import _is_allowed_by_comment

__all__ = [
    "Rule",
    "Issue",
    "ProviderReplacement",
    "FMChecker",
    "_is_allowed_by_comment",
    "SCOPE_ANY",
    "SCOPE_RESEARCH_SCRIPT",
    "SCOPES",
    "REQUIRED_CAPABILITIES",
    "is_research_script",
    "is_test_file",
]
