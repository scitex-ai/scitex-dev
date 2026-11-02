---
description: |
  [TOPIC] Interfaces Overview
  [DETAILS] Five default interfaces: Python API, CLI, MCP, Web API and skills. Leaf packages own implementations; Dev dispatches shared source-binding audits and hooks; SDK owns Web API descriptors, routes, schemas and admission. Intentional omissions require explicit narrow reasons. Implementation, host enablement and live availability are separate facts.
tags: [scitex-general-interface-overview]
---

# Five Interfaces (Default per Package)

Almost every SciTeX package must expose these five predictable interfaces.
Keep domain logic in its Python API; other interfaces are thin adapters.
A specific interface that does not apply needs a recorded, narrow reason.

| Interface | Owner of implementation | Shared contract/checks |
|---|---|---|
| Python API | Leaf public facade and operations | Dev API and source-binding audits |
| CLI | Leaf command bindings | Dev CLI conventions and source-binding audit |
| MCP | Leaf server/tool bindings | Dev MCP conventions and source-binding audit |
| Web API | Leaf SDK `ApiPlugin` declaration and handlers | SDK descriptors, schemas, routes, errors, scopes and admission |
| Skills | Leaf packaged instructions | Dev skill discovery and source-binding audit |

Dev's existing `scitex_dev.audit.project` provider reports five default errors:
`PS-IF-001` Python, `PS-IF-002` CLI, `PS-IF-003` MCP, `PS-IF-004` Web,
and `PS-IF-005` skills. It reads the explicit repository's source and metadata,
without importing its modules or starting servers. Empty handlers, dangling
entry points and unproven dynamic bindings do not demonstrate an implementation.
Detailed behavior and operation parity remain separate API/CLI/MCP/SDK/skills
checks: a static binding is not proof that every advertised operation works.

The executable `dev.five-interface-commit` and
`dev.five-interface-changed-source` hooks use the same checker. The commit gate
checks ordinary `git commit` invocations; the post-tool gate checks actual
relevant changed interface source/metadata. Neither executes a package's code.
These are installed through the existing Dev hooks provider; a declaration in
a package is not proof that a particular agent has enabled the dispatcher.

## Narrow exceptions

Use the existing `.scitex/dev/config.yaml` per-rule/site mechanism. For example,
an offline secret-processing package may justify withholding its Web adapter:

```yaml
project-type: [pip]
audit:
  exemptions:
    PS-IF-004:
      - path: pyproject.toml
        line: 1
        reason: "This offline signing utility must not expose private-key operations through HTTP."
```

The rule/site and substantive reason must match; blank/placeholder reasons,
wildcard paths and a different line do not exempt a missing binding. Accepted
exceptions remain visible as informational findings. Do not copy the example
as a way to silence ordinary implementation work.

## Implementation and deployment are different

Declare a real Web API using the SDK's `scitex.apis` contract. Its presence
neither starts a server nor admits a route: host configuration must explicitly
enable reviewed routes. Keep optional Web runtime imports off the basic Python
and CLI paths. Report source implementation, host enablement and live
availability independently. Installed skills should be discoverable by default,
with explicit opt-outs; the default does not imply every host installed them.

## Sub-skills

- [01_python-api/](01_python-api/) — public source of truth and lazy exports
- [02_cli/](02_cli/) — predictable noun/verb commands and introspection
- [03_mcp/SKILL.md](03_mcp/SKILL.md) — real tools and schemas
- [04_skills/](04_skills/) — packaged instructions and discovery
- [05_http-api/](05_http-api/) — SDK Web contracts and host enablement
