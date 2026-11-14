"""Shared fixtures for the linter tests.

Strips ambient ``SCITEX_(DEV_)LINTER_*`` environment variables so the
config-discovery / precedence tests are hermetic. Without this, a developer's
or CI runner's profile that exports e.g. ``SCITEX_DEV_LINTER_ENABLE=FM`` leaks
through ``config._load_env`` into ``load_config`` and breaks tests asserting a
clean default config (observed on the self-hosted Spartan runners, whose
profile sets exactly that var).
"""

from __future__ import annotations

import os

import pytest

_LINTER_ENV_PREFIXES = ("SCITEX_DEV_LINTER_", "SCITEX_LINTER_")


@pytest.fixture(autouse=True)
def _isolate_linter_env():
    """Remove ambient SCITEX linter env vars around each linter test."""
    saved = {
        key: value
        for key, value in os.environ.items()
        if key.startswith(_LINTER_ENV_PREFIXES)
    }
    for key in saved:
        del os.environ[key]
    try:
        yield
    finally:
        for key in [k for k in os.environ if k.startswith(_LINTER_ENV_PREFIXES)]:
            del os.environ[key]
        os.environ.update(saved)


@pytest.fixture
def observe_lint():
    """Observe real engine rule requests and returned issues without replacing either.

    A request can be filtered by availability, comments or configuration.
    Algorithm tests can inspect requests while separate assertions check the
    actual emitted issues. The previous profiler is restored after each call.
    """
    import sys
    from scitex_dev.linter.checker import SciTeXChecker, lint_source

    def run(source, *, filepath="module.py", config=None):
        requests = []
        previous = sys.getprofile()

        def record(frame, event, arg):
            if event == "call" and frame.f_code is SciTeXChecker._add.__code__:
                rule = frame.f_locals.get("rule")
                if rule is not None:
                    requests.append(rule)

        sys.setprofile(record)
        try:
            issues = lint_source(source, filepath=filepath, config=config)
        finally:
            sys.setprofile(previous)
        return requests, issues

    return run
