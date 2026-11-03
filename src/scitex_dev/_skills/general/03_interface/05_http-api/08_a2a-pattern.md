---
description: |
  [TOPIC] 08 a2a pattern
  [DETAILS] A2A and the general Web API are distinct transports.
tags: ['scitex-general-interface-http-api-a2a-pattern']
---

# Agent protocols

A2A is a specialized agent protocol, not the general SDK Web API contract.
Consult scitex-agent-container's current protocol source and skills for its
endpoint, authentication and lifecycle behavior. Do not duplicate those rules
in Dev or require unrelated leaf packages to implement an agent host.

Expose shared business capabilities through the same Python API. Qualify each
transport separately; an A2A listener does not prove MCP or SDK Web routes work.
