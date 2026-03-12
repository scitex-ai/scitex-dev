#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scitex-dev: Shared developer utilities for the SciTeX ecosystem.

Zero-dependency package providing:
- Docs aggregation and serving across all scitex packages
- Result type with return_as="result" pattern
- CLI and MCP utilities for LLM-friendly interfaces
"""

__version__ = "0.1.0"

from .docs import build_docs, get_docs, search_docs
from .search import search

__all__ = ["get_docs", "build_docs", "search_docs", "search", "__version__"]
