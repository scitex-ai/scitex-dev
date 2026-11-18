CLI documentation adapters
==========================

A leaf package can add documentation commands through the shared argparse or
Click adapter. Both adapters dispatch to the same package documentation reader.
They register ``docs list`` and ``docs get``; they do not add Dev's global search,
validation or provider-catalog commands to the leaf.

Usage
-----

These commands run against Dev's own registered documentation. Replace
``scitex-dev`` with a leaf's executable when that leaf mounts the adapter.
Use the page names returned by ``list`` rather than assuming every package
ships the same pages.

.. code-block:: bash

   # List available documentation pages
   scitex-dev docs list

   # Get the page index as structured JSON
   scitex-dev docs list --json

   # Show the same page index through get
   scitex-dev docs get --json

   # Read a listed HTML page
   scitex-dev docs get cli

   # Select the HTML format explicitly
   scitex-dev docs get cli --format html

``--json`` on a page listing describes the index, not the content of every page.
Page-specific JSON requires the provider's JSON build assets. The current
reader can fall back to package introspection when a requested JSON page is
unavailable; do not treat that fallback as the requested page's content.
The removed flat flags ``docs --list``, ``docs --page`` and ``docs --tldr``
are not the adapter interface.

Integration (argparse)
----------------------

Replace ``your-package`` with the installed distribution name whose
``scitex_dev.docs`` declaration points to its Python package. The executable
name and documentation-provider name can differ.

.. code-block:: toml

   [project.entry-points."scitex_dev.docs"]
   your-package = "your_package"

.. code-block:: python

   import argparse

   from scitex_dev.cli import register_docs_subcommand

   parser = argparse.ArgumentParser(prog="my-tool")
   subparsers = parser.add_subparsers(dest="command")
   register_docs_subcommand(subparsers, package="your-package")

The caller parses arguments and invokes the selected subcommand's ``func``
callback. Registering the parser alone does not execute a documentation read.

Integration (Click)
-------------------

.. code-block:: python

   import click

   from scitex_dev.cli import docs_click_group

   @click.group()
   def cli():
       pass

   cli.add_command(docs_click_group(package="your-package"))

A direct custom mount can use ``docs_click_group(package="your-package",
name="manual")``; its examples use ``manual``. The adapter still exposes only
``list`` and ``get``. Dev separately registers ``scitex-dev docs search``,
``docs validate`` and ``docs list-providers`` in its own dispatcher.

Verification and scope
----------------------

The owning adapters are ``_core/dispatch/_docs_argparse.py`` and
``_core/dispatch/_docs_click.py``. Their real parser, dispatch and
advertised-example controls live under
``tests/scitex_dev/_core/dispatch/``; Dev-only commands have controls in
``tests/scitex_dev/_cli/test__docs_cmds.py``. Generated HTML and installed
package resources need separate content and source-binding checks.
Provider discovery or a successful local command does not establish a live
hosted route.

API
---

.. autofunction:: scitex_dev.cli.register_docs_subcommand
   :no-index:
.. autofunction:: scitex_dev.cli.docs_click_group
   :no-index:
