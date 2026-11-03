---
description: |
  [TOPIC] 03 endpoint conventions
  [DETAILS] SDK-owned route and schema declarations.
tags: ['scitex-general-interface-http-api-endpoint-conventions']
---

# Endpoint declarations

Register a literal SDK `ApiPlugin` data object through `scitex.apis`. Use the
SDK's `ApiRoute` constructors and schema contracts, normalized relative routes,
unique operation IDs and owned handler references. Read the SDK-owned contract
skill for the current constructors rather than copying a competing schema here.

Hosts decide the final mount prefix and admission policy. Descriptor discovery
does not expose a route. Generate OpenAPI from the descriptor; a public `/docs`
page is a deployment decision, not a universal requirement.
