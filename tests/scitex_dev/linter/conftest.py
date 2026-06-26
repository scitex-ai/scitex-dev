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
