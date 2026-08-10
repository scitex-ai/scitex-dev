#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/_cli/ci/__init__.py
"""``scitex-dev ci`` CLI package."""

from ._mergeable_cmd import register_ci_commands

__all__ = ["register_ci_commands"]
