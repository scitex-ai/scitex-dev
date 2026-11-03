---
description: |
  [TOPIC] 07 cli integration
  [DETAILS] Discover real CLI routes instead of assuming a Web launch command.
tags: ['scitex-general-interface-http-api-cli-integration']
---

# CLI integration

Inspect the leaf's actual `--help`. Not every package provides `http start`:
host-mounted SDK adapters need no separate leaf daemon. Document only existing
launch commands, flags and environment variables, and distinguish standalone
launch from host enablement.

Use the existing Dev hook installation workflow for SDK-owned Web checks.
Inspect installed provider entry points before claiming a rule is available.
Installing hook bindings does not prove a running client has loaded them;
post-shell checks report after an operation and cannot prevent it.
