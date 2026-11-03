---
description: |
  [TOPIC] 04 error envelope
  [DETAILS] Error responses must follow the owned API contract.
tags: ['scitex-general-interface-http-api-error-envelope']
---

# Errors

Use the response schemas and status behavior declared by the leaf's SDK Web
contract. Translate Python errors in the thin transport adapter; do not invent
an unrelated global envelope or claim every existing service already uses it.

Return useful typed reasons without credentials, tracebacks or private paths.
Test invalid input, authorization failure, missing dependencies and unsupported
methods using owned fixtures. A static schema check does not prove these paths
execute correctly.
