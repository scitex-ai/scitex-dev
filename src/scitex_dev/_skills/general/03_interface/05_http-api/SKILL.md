---
description: |
  [TOPIC] SKILL
  [DETAILS] Web API interface ownership, SDK contracts and evidence limits.
tags: ['scitex-general-interface-http-api-index']
---

# Web API — index

Web API is a default interface target alongside Python, CLI, MCP and skills.
A justified exception is appropriate when it is inapplicable. A missing or
placeholder implementation is a gap, not a successful audit.

scitex-sdk owns the contract; leaves own descriptors and handlers; scitex-dev
discovers leaf audit/hook providers. Hosts explicitly admit and mount routes.
A framework choice alone proves none of these things.

Read the SDK-owned `scitex-app/24_web-api-contract.md` from an installation that
contains that skill and its provider entry points. The shared execution workflow
is [the five-interface audit](../../../scitex-dev/39_interface-audit.md).

- [Overview](01_overview.md): ownership and transport boundaries
- [Framework choice](02_framework-choice.md): standalone versus host adapters
- [Endpoints](03_endpoint-conventions.md): descriptors and schema ownership
- [Errors](04_error-envelope.md): contract-specific responses
- [Health](05_health-and-ops.md): runtime qualification
- [Authentication](06_auth.md): explicit host admission and authorization
- [CLI](07_cli-integration.md): inspect actual supported commands
- [Agent protocol](08_a2a-pattern.md): A2A is a separate transport
- [Audit checklist](09_audit-checklist.md): source and live evidence
- [Remaining work](TODO.md): gaps and non-existent commands
