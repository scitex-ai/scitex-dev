"""Auditor freshness self-check — is the auditor I'm about to run current?

Background — 2026-05: a user ran `scitex-dev ecosystem audit-all
scitex-io` against scitex-io's modernised README and got six false-
positive errors (PS-131, PS-141, PS-142, etc.). Cause: the installed
auditor was 0.11.8 while PyPI was on 0.11.11 — three relaxations
shipped in between. The rule corpus had moved; the local auditor
hadn't. So the audit CLI runs this self-check first and warns (never
blocks) if the running auditor is behind what shipped.

THE FOSSIL BUG THIS MODULE USED TO HAVE
---------------------------------------
The original self-check read ``scitex_dev.__version__`` (via
``importlib.metadata``) and string-compared it to PyPI's latest. That
metadata is a FOSSIL for an *editable* checkout — it is frozen at
``pip install -e`` and says nothing about the code actually loaded. On
the operator's own box (scitex-dev is an editable checkout there), that
comparison could FALSELY report "you are behind" and hand back a
``pip install -U`` remedy — which would CLOBBER his editable checkout
with a wheel. That is exactly the danger the version-currency primitive
was built to prevent, so this self-check now DOGFOODS it.

WHAT IT DOES NOW
----------------
:func:`warn_if_stale` delegates to
:func:`scitex_dev.versioning.check_currency`, then maps the ONE finding
that answers "is my running auditor behind?" — ``install-currency`` —
onto the old warn/return contract:

* FRESH   -> no warning, ``False``. (An editable checkout whose working
  tree carries every released commit is FRESH BY CONTENT, so this is the
  no-clobber case: it never fires and never suggests ``pip install -U``.)
* STALE   -> the yellow WARN line, carrying the primitive's remedy
  (``git pull`` for an editable checkout, ``pip install -U`` only for a
  wheel) and the name-the-binary tag (origin + interpreter), then
  ``True``.
* UNKNOWN -> no warning, ``False``. Offline / can't-tell must NEVER be
  dressed up as "you are behind" — that was the second half of the
  fossil bug.

Only the ``install-currency`` finding is consulted: the primitive's
other checks (ghost-tag, release-run, running-vs-installed) are about
the SHIPPING pipeline, not "is my running auditor stale", and an audit
of some *other* package is the wrong place to raise them.

Behaviour can be turned off explicitly with --no-version-check or by
setting SCITEX_DEV_SKIP_VERSION_CHECK=1. SCITEX_DEV_VERSION_CHECK_SILENT=1
suppresses the print while still returning True so a caller can react.
"""

from __future__ import annotations

import os
import sys

from ...versioning import Currency, VersioningConfig, check_currency

__all__ = ["config", "warn_if_stale"]

_INSTALL_CURRENCY = "install-currency"


def config() -> VersioningConfig:
    """The version-currency config for scitex-dev checking ITSELF.

    Only ``install-currency`` matters for the auditor-staleness question,
    so the release-run and running-vs-installed checks are left disabled
    (``release_workflow`` / ``systemd_unit`` unset) — that keeps the
    self-check off ``gh`` / ``systemctl`` and honest about its scope.
    """
    return VersioningConfig(dist="scitex-dev", module="scitex_dev")


def warn_if_stale(*, stream=sys.stderr, sources=None) -> bool:
    """Warn (once, to stderr) if the running auditor is genuinely behind.

    Returns True iff a stale warning was warranted (emitted, unless
    silenced), False otherwise. Never raises: any failure in the currency
    probe degrades to silence so the self-check can never break an audit.

    Honors:
      - SCITEX_DEV_SKIP_VERSION_CHECK=1 — skip the check entirely
      - SCITEX_DEV_VERSION_CHECK_SILENT=1 — suppress the print (still
        returns True so a caller can react)

    ``sources`` defaults to live PyPI/git/install evidence; tests pass a
    ``StaticSources`` to drive the tri-state from recorded facts.
    """
    if os.environ.get("SCITEX_DEV_SKIP_VERSION_CHECK"):
        return False

    try:
        report = check_currency(config(), sources=sources)
    except Exception:
        return False  # a self-check must never break the audit

    finding = next(
        (f for f in report.findings if f.check == _INSTALL_CURRENCY), None
    )
    if finding is None or finding.state is not Currency.STALE:
        # FRESH (incl. editable-current: no clobber) and UNKNOWN
        # (offline / can't-tell) are both silent — only positive evidence
        # of staleness speaks.
        return False

    if not os.environ.get("SCITEX_DEV_VERSION_CHECK_SILENT"):
        lines = [f"WARN  scitex-dev auditor is stale: {finding.summary}"]
        if finding.remedy:
            lines.append(f"      fix: {finding.remedy}")
        lines.append("      (silence: --no-version-check)")
        msg = "\033[33m" + "\n".join(lines) + "\033[0m"
        print(msg, file=stream, flush=True)
    return True
