Pre-Push Gate
=============

The pre-push gate is a versioned, distributable ``git`` hook that
runs ``scitex-dev``'s audit + scope tests **before** ``git push``
proceeds. It exists to stop the "push → CI red → push fix → CI red
again" merry-go-round: the gate catches what local verification
should have caught, with a budget tight enough (60s) that operators
don't reach for ``--no-verify`` out of frustration.

Red-Green Doctrine
------------------

The gate runs the SAME two checks that gate ``Test`` in CI, but
restricted to the FAST subset:

1. ``scitex-dev ecosystem audit-all <pkg> --path <repo> --severity error``
   — the same audit gate
   ``tests/develop/test_audit.py`` runs (installed by
   ``scitex-dev ecosystem install-audit-gate``), so local + CI agree
   byte-for-byte.
2. ``pytest --testmon -m "not slow and not integration"`` — only tests
   whose imported sources changed since the last green run, with
   heavy markers excluded.

Heavy tests (``slow``, ``integration``, network-bound) stay in CI.
The local gate is the FAST check that catches the obvious red, not
a CI replacement.

Installation
------------

The gate ships inside ``scitex-dev`` as
``scitex_dev._hooks.pre-push.sh``. Operators install it per-repo
with one command:

.. code-block:: bash

   scitex-dev hooks enable-pre-push --target ~/proj/<package>

This does two things in one step:

1. Symlinks the bundled ``pre-push.sh`` into
   ``<target>/.githooks/pre-push``.
2. Runs ``git -C <target> config core.hooksPath .githooks`` so the
   symlink actually fires (without ``core.hooksPath`` set, ``git``
   only looks under ``.git/hooks/`` and the symlink is a no-op).

Because the deploy artefact is a SYMLINK (not a copy), every
``scitex-dev`` upgrade automatically propagates the latest gate
logic to every repo that ran ``enable-pre-push`` once. This is the
same anti-drift mechanism the bundled ``run_lint.sh`` uses (Pillar
0, #169).

Verifying the Install
---------------------

.. code-block:: bash

   scitex-dev hooks list --target ~/proj/<package>

Expected output includes ``ok  pre_push  → <repo>/.githooks/pre-push``.

Bypass
------

The gate is **safe-by-default**, not **no-escape**. Two bypass
paths exist for genuine emergencies:

- ``SCITEX_DEV_SKIP_PREPUSH=1 git push`` — env-var bypass, one-shot.
- ``git push --no-verify`` — git's native escape hatch.

Both print a notice to stderr so the choice is visible in agent
transcripts. Use sparingly: CI will still run the full audit, so
bypassing the local gate just defers the red signal.

Distributing to Other Ecosystem Packages
----------------------------------------

The CLI accepts any repo with a ``pyproject.toml`` as ``--target``:

.. code-block:: bash

   scitex-dev hooks enable-pre-push --target ~/proj/figrecipe
   scitex-dev hooks enable-pre-push --target ~/proj/scitex-io
   scitex-dev hooks enable-pre-push --target ~/proj/socialia

The hook script identifies the package by parsing
``[project] name`` from ``pyproject.toml`` (falling back to the repo
basename). The same script + the same ``scitex-dev`` binary runs
the same checks across every package — no per-package
configuration.

CLI Reference
-------------

.. code-block:: text

   scitex-dev hooks enable-pre-push --target <repo>
       Install the canonical pre-push gate AND wire core.hooksPath.

   scitex-dev hooks install --name pre_push --target <repo>
       Install ONLY the symlink (skip the core.hooksPath wiring).
       Use this when the target repo manages core.hooksPath itself.

   scitex-dev hooks list --target <repo>
       Show install status of every known hook.

   scitex-dev hooks update --target <repo>
       Re-point the symlink at the current bundled script (used after
       a scitex-dev upgrade that changed the script — should be rare,
       symlinks usually pick this up automatically).

   scitex-dev hooks print-path pre_push
       Print the absolute filesystem path of the bundled script.
