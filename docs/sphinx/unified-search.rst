Unified Search
==============

Search the local legacy documentation mapping: entry-point declarations plus
installed ECOSYSTEM fallbacks. The indexes below describe metadata or selected
source text; hits do not establish registered tools, callable handlers or live
availability. Some searches initialize package code.

Query Syntax
------------

Google-like query operators:

.. list-table::
   :header-rows: 1

   * - Syntax
     - Meaning
     - Example
   * - ``word``
     - Optional term (boosts score)
     - ``search("save figure")``
   * - ``+word``
     - Required term (must match)
     - ``search("+ttest stats")``
   * - ``-word``
     - Excluded term (must NOT match)
     - ``search("stats -deprecated")``
   * - ``"phrase"``
     - Exact phrase match
     - ``search('"save figure"')``

Scopes
------

.. list-table::
   :header-rows: 1

   * - Scope
     - Searches
   * - ``all``
     - Union of these four local indexes (default)
   * - ``api``
     - Shallow API introspection: exported functions/classes and inspected methods
   * - ``cli``
     - Matching console-script entry-point names and targets; no subcommand traversal
   * - ``mcp``
     - Function names/docstrings in selected direct source files; registration unchecked
   * - ``docs``
     - Manifest page names/titles and package description; page bodies are not searched

Index boundaries and evidence
-----------------------------

API introspection can initialize targets and describes submodules without
recursively searching their members. MCP text search reads non-underscore
``*.py`` files directly under ``_mcp_tools``, ``mcp`` or ``_mcp``; it does not
walk nested directories or verify FastMCP registration. Documentation search
reads manifest metadata, not HTML or document bodies. Console-script metadata
is separate from loading a command or enumerating its subcommands.

Query matching is fuzzy by default, including required terms. Use
``fuzzy=False`` to disable approximate term matching. Terms and quoted phrases
still match case-insensitive substrings. The owning implementations are ``_docs/search.py``,
``_core/discovery.py`` and ``_core/introspect.py``. Existing query controls live
in ``tests/scitex_dev/_docs/test_search.py`` (``TestParseQuery`` and
``TestScoreText``). Those controls do not qualify every installed provider or
complete whole-search behavior.

API
---

.. autofunction:: scitex_dev._docs.search.search
.. autofunction:: scitex_dev._docs.search.parse_query
.. autofunction:: scitex_dev._docs.search.score_text
