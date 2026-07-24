"""Shared logging-emit helper for every `scitex-dev ecosystem audit-*` command.

The auditor headlines (`ok` / `warn` / `error` / `info` / `skip`) need to
be color-aware AND severity-aware so CI can grep the level prefix and
humans can scan the colored output. Both come from scitex-logging.

Falls back to `click.echo` with the legacy plain-text headline prefix
when scitex-logging is unavailable, so the auditor is still functional
in pristine venvs that haven't installed the dep yet.

Logger-class name race
----------------------
`scitex_logging.getLogger` **is** `logging.getLogger` (verified by
identity). scitex-logging keeps no registry of its own: it calls
`logging.setLoggerClass(SciTeXLogger)` at import time, so a logger's
class is decided by whatever `setLoggerClass` state was live when that
NAME was first created — and `Logger.manager` caches that object forever.

If anything creates the name `scitex_dev.audit` through the stdlib before
scitex-logging is imported (a pytest fixture calling
`caplog.set_level(level, logger="scitex_dev.audit")` is the observed
case), we are permanently handed a plain `logging.Logger`, which has no
`.success` method — and every auditor died with
`AttributeError: 'Logger' object has no attribute 'success'`.

Importing this module earlier does NOT fix that: the poisoning happens
whenever anything wins the name, including a conftest evaluated before
`scitex_dev` is imported at all. So the level dispatch below is resolved
per call and never assumes the custom methods exist. (The old dispatch
built its method table eagerly, dereferencing `.success` on EVERY call,
so even `emit("info", ...)` crashed on a poisoned logger.)

The fallback is NOT a downgrade. scitex-logging registers its level
NUMBERS globally on the `logging` module (`SUCCESS` = 31 -> `"SUCC"`),
not on the logger class, so a plain `Logger` reaches the identical
levelno/levelname via `Logger.log(SUCCESS, text)`. Grep parity and CI
severity parity are preserved exactly; only scitex-logging's unused
presentation kwargs (indent/sep/color) are out of reach, and `emit`
passes none of them.

The degraded path is still announced once at WARNING and recorded in
`degraded_reason()`, so it can never pass for a healthy run — a degrade
branch that leaves no trace is where a hard failure hides
(`_skills/general/09_quality/04_verification-controls.md` §8).
"""

from __future__ import annotations

import logging

import click

try:
    import scitex_logging as _stx_log

    _logger = _stx_log.getLogger("scitex_dev.audit")
    _SUCCESS = _stx_log.SUCCESS
except ImportError:  # pragma: no cover — scitex-logging is a hard runtime dep
    _logger = None
    _SUCCESS = logging.INFO


_LEGACY_PREFIX = {
    "info": "info",
    "warning": "warn",
    "error": "error",
    "success": "ok",
    "skip": "skip",
}

# level name -> (numeric level, logger method that renders it best).
# `skip` deliberately shares INFO with `info`; only its legacy prefix differs.
_LEVELS: dict[str, tuple[int, str]] = {
    "info": (logging.INFO, "info"),
    "warning": (logging.WARNING, "warning"),
    "error": (logging.ERROR, "error"),
    "success": (_SUCCESS, "success"),
    "skip": (logging.INFO, "info"),
}

# Set when a poisoned (plain `logging.Logger`) instance forced the
# `Logger.log(levelno, ...)` route. Read it via `degraded_reason()`.
_degraded_reason: str | None = None


def degraded_reason() -> str | None:
    """Why the emit path is degraded, or ``None`` when it is healthy.

    Non-``None`` means the `scitex_dev.audit` logger lost the name race
    and is a plain `logging.Logger`. Levels still render correctly (see
    the module docstring) but scitex-logging's own methods are gone.
    Callers that summarise a run should surface this, so the degrade is
    visible where the result is READ, not only where it happened.
    """
    return _degraded_reason


def _announce_degraded(logger: logging.Logger, level: str) -> None:
    """Announce the lost name race exactly once, at WARNING."""
    global _degraded_reason
    if _degraded_reason is not None:
        return
    _degraded_reason = (
        "logger 'scitex_dev.audit' is a plain logging.Logger, not a "
        "SciTeXLogger: something created that logger name through the "
        "stdlib before scitex_logging was imported, and logging caches "
        f"the class per name forever (first missing method: .{level}). "
        "Levels still render correctly via Logger.log(); scitex-logging "
        "formatting is unavailable for this process."
    )
    # `.warning` exists on every Logger, poisoned or not.
    logger.warning(f"audit emit degraded: {_degraded_reason}")


def emit(
    level: str,
    text: str,
    *,
    err: bool = False,
    logger: logging.Logger | None = None,
) -> None:
    """Emit `text` at `level` through scitex-logging when available.

    Parameters
    ----------
    level
        One of ``info`` / ``warning`` / ``error`` / ``success`` / ``skip``.
        ``skip`` falls through to ``info`` at the logging layer; the
        legacy prefix path keeps the `skip ` headline for grep parity.
    text
        Message body. The level prefix is added automatically.
    err
        Route to stderr in the fallback path. Ignored by the
        scitex-logging path (which honours the logger's own stream
        configuration).
    logger
        Emit through this logger instead of the module-level
        `scitex_dev.audit` one. The injection seam that lets a caller
        (or a test) supply a real logger whose class is known, rather
        than depending on process-global `setLoggerClass` history.
    """
    target = _logger if logger is None else logger
    if target is not None:
        levelno, method = _LEVELS.get(level, _LEVELS["info"])
        fn = getattr(target, method, None)
        if fn is None:
            # Lost the logger-class name race — announce, then emit at the
            # SAME numeric level so the rendered levelname is unchanged.
            _announce_degraded(target, method)
            target.log(levelno, text)
            return
        fn(text)
        return
    prefix = _LEGACY_PREFIX.get(level, "info")
    click.echo(f"{prefix}  {text}", err=err)
