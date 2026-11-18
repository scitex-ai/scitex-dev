Quick Start
===========

Installation
------------

.. code-block:: bash

   pip install scitex-dev

Docs Aggregation
----------------

.. code-block:: python

   from scitex_dev import get_docs, build_docs

   # All installed packages
   get_docs()

   # Single package
   get_docs(package="scitex-writer", format="json")

   # Build requires the docs extra and the package documentation sources
   build_docs(package="scitex-writer")

Unified Search
--------------

.. code-block:: python

   from scitex_dev import search

   search("save figure")                      # search everything
   search("ttest", scope="api")               # Python API only
   search('+required -excluded "phrase"')      # Google-like syntax

CLI Mixin
---------

A leaf can mount the shared ``docs list`` and ``docs get`` adapters.
Dev's own registered documentation can be inspected with:

.. code-block:: bash

   scitex-dev docs list
   scitex-dev docs list --json
   scitex-dev docs get cli

See :doc:`cli` for adapter registration, format limits and verified command scope.
