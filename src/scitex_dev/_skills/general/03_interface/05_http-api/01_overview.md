---
description: |
  [TOPIC] 01 overview
  [DETAILS] Web API ownership and thin adapters.
tags: ['scitex-general-interface-http-api-overview']
---

# Ownership

Python APIs contain business logic. A leaf's Web adapter exposes an explicit
subset through an SDK `ApiPlugin` descriptor. Keep scopes, schemas and side
effects in that contract; avoid a second business implementation in the host.

scitex-dev dispatches checks, scitex-sdk owns Web contract validation, and the
host owns route admission and deployment. Source validation, installed provider
discovery, host enablement and live behavior require separate evidence.
