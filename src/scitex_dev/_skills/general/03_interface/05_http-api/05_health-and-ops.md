---
description: |
  [TOPIC] 05 health and ops
  [DETAILS] Separate API declaration checks from runtime qualification.
tags: ['scitex-general-interface-http-api-health-and-ops']
---

# Runtime qualification

Host operators own readiness, health routing, CORS, request limits, logs and
metrics for the deployed service. A leaf descriptor does not require a separate
server, port, `/health` route or `/metrics` endpoint.

Qualify the actual host routes and dependency failures with owned requests.
Record origin, version and timestamp. Keep installed discovery, enabled routes
and live responses separate; source checks do not prove availability.
