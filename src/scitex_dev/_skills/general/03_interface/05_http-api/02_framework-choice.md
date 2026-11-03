---
description: |
  [TOPIC] 02 framework choice
  [DETAILS] Framework choice without overriding the SDK contract.
tags: ['scitex-general-interface-http-api-framework-choice']
---

# Framework choice

Use SDK Web API contracts for host-integrated leaf endpoints. A Django host
adapter and a standalone server can share Python logic without sharing a server
framework. This interface policy does not require migrating existing Flask,
Starlette or other services merely to satisfy a framework-name check.

For a standalone service, choose and document its framework, launch command,
dependencies and security boundary. Do not infer a mandatory FastAPI service,
new port or new daemon for every package.
