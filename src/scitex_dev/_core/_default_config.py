#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: scitex_dev/_core/_default_config.py

"""Default ``config.yaml`` template + writer.

Extracted from ``config.py`` (which exceeded the line budget). ``config.py``
re-exports :func:`create_default_config` so existing imports keep working.
"""

from __future__ import annotations

from pathlib import Path

_DEFAULT_CONFIG = """\
# SciTeX Developer Configuration
# Timestamp: 2026-02-02

# Ecosystem packages to track
packages:
  - name: scitex
    local_path: ~/proj/scitex-python
    pypi_name: scitex
    github_repo: ywatanabe1989/scitex-python
    import_name: scitex
  - name: figrecipe
    local_path: ~/proj/figrecipe
    pypi_name: figrecipe
    github_repo: ywatanabe1989/figrecipe
    import_name: figrecipe
  - name: scitex-hub
    local_path: ~/proj/scitex-hub
    pypi_name: scitex-hub
    github_repo: ywatanabe1989/scitex-hub
    import_name: scitex_hub
  - name: scitex-writer
    local_path: ~/proj/scitex-writer
    pypi_name: scitex-writer
    github_repo: ywatanabe1989/scitex-writer
    import_name: scitex_writer
  - name: crossref-local
    local_path: ~/proj/crossref-local
    pypi_name: crossref-local
    github_repo: ywatanabe1989/crossref-local
    import_name: crossref_local

# Hosts to check via SSH
hosts:
  - name: ywata-note-win
    hostname: localhost
    user: ywatanabe
    role: dev
    enabled: true
  - name: nas
    hostname: nas.local
    user: ywatanabe
    role: staging
    enabled: true
  - name: scitex-hub
    hostname: scitex.ai
    user: deploy
    role: prod
    enabled: false

# GitHub remotes to check
github_remotes:
  - name: ywatanabe1989
    org: ywatanabe1989
    enabled: true
  - name: scitex-ai
    org: scitex-ai
    enabled: false

# PyPI accounts
pypi_accounts:
  - name: ywatanabe1989
    enabled: true

# Branches to track
branches:
  - main
  - develop
"""


def create_default_config(config_path: Path) -> Path:
    """Write the default config to ``config_path`` if it doesn't exist.

    The caller resolves + creates the parent directory; this function only
    writes the template when the file is absent, then returns the path.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        return config_path
    config_path.write_text(_DEFAULT_CONFIG)
    return config_path


# EOF
