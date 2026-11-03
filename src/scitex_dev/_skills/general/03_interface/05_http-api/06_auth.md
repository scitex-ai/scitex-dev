---
description: |
  [TOPIC] 06 auth
  [DETAILS] Explicit host admission and per-operation authorization.
tags: ['scitex-general-interface-http-api-auth']
---

# Authentication and authorization

Hosts explicitly decide `ApiAdmission` before resolving or enabling handlers.
The leaf declares its authentication, scope and idempotency requirements through
the SDK contract. Enforce authorization for the actual resource and operation;
a descriptor or installed provider is not a grant of access.

Do not trust a client-supplied `X-Forwarded-User` as authenticated identity.
Proxy identity requires a documented trusted ingress that strips untrusted
headers. Do not put tokens in URLs. Test denied access and tenant isolation as
well as successful authorized requests. This guide does not prescribe an
unimplemented `scitex_dev.http.require_token` helper.
