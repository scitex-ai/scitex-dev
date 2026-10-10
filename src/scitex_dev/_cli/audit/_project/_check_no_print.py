"""Compatibility imports for the logging-owned PS-220 project auditor.

The owning distribution supplies rule metadata and detection through
``scitex_dev.audit.project``. Existing direct imports remain supported;
the project runner invokes the discovered provider exactly once.
"""

from scitex_logging._output_auditor import (
    PRINT_FORBIDDEN_RULES,
    _DEFAULT_SEVERITY as _DEFAULT_SEVERITY,
    check_ps220_no_print,
    resolve_ps220_severity,
)

__all__ = [
    "PRINT_FORBIDDEN_RULES",
    "check_ps220_no_print",
    "resolve_ps220_severity",
]
