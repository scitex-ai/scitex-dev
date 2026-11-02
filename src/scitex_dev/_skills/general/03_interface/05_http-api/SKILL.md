---
description: |
  [TOPIC] Interface Http Api
  [DETAILS] Default Web API implementation contract for SciTeX packages — SDK descriptors and explicit host enablement, framework choice (FastAPI canonical for REST; aiohttp when WebSocket is genuinely needed; Starlette only when an SDK forces it), REST endpoint conventions, JSON error envelope, `/health` and observability, auth posture (canonical: nginx reverse proxy in front; helper middleware for dev), CLI integration, and the A2A specialty pattern for agent packages. Use when adding HTTP endpoints to a package, choosing a framework, or auditing an existing HTTP server against the ecosystem convention.
tags: [scitex-general-interface-http-api-index]
---

# Web API — Index

Almost every leaf provides a real SDK Web API binding, or records a specific
reasoned exception. Implementation is required by default; running an HTTP
server and enabling its routes remain explicit host decisions. Dev dispatches
the SDK-owned descriptor/schema/routing checks and its generic presence check.
See [the five-interface contract](../00_overview.md) for ownership and exceptions.

Domain operations stay in the owning leaf's Python API. Declare adapters
through SDK `ApiPlugin` data registered in `scitex.apis`, with reviewed routes,
request/response schemas, errors, auth/scope and rate semantics. Do not load
private Hub code or start a server just to discover declarations.

The sections below describe transport implementation details. They do not
supersede SDK ownership of Web API contracts or authorize host admission.

## Sections

1. [01_overview.md](01_overview.md) — when to use HTTP, delegation rule, the 3 transport shapes
2. [02_framework-choice.md](02_framework-choice.md) — FastAPI canonical / aiohttp / Starlette / discouraged options
3. [03_endpoint-conventions.md](03_endpoint-conventions.md) — REST routes, HTTP verbs, JSON shape, OpenAPI `/docs`
4. [04_error-envelope.md](04_error-envelope.md) — Pydantic ErrorResponse, HTTP status codes, `ErrorCode` integration
5. [05_health-and-ops.md](05_health-and-ops.md) — `/health`, CORS, caching, observability
6. [06_auth.md](06_auth.md) — nginx reverse proxy canonical; shared middleware for local dev
7. [07_cli-integration.md](07_cli-integration.md) — `<cli> http start` subcommand, port conventions, env vars
8. [08_a2a-pattern.md](08_a2a-pattern.md) — A2A specialty for agent packages (one-off, not generalizable)
9. [09_audit-checklist.md](09_audit-checklist.md) — release-gate checklist
10. [TODO.md](TODO.md) — drift fixes + planned `audit-http` linter
