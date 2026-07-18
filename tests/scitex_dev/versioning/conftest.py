#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Real environment manipulation — no monkeypatch.

``os.environ`` IS the production collaborator here: ``_cache`` and ``_warn``
read it live, on purpose, so a container or a test can redirect them. The
honest way to test that is to set the real variable and put it back
afterwards — which is all this fixture does.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def env():
    """Set/unset real env vars for one test; restore exactly on teardown."""
    saved: dict[str, str | None] = {}

    def _set(name: str, value: str | None) -> None:
        if name not in saved:
            saved[name] = os.environ.get(name)
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

    yield _set

    for name, old in saved.items():
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old


# EOF
