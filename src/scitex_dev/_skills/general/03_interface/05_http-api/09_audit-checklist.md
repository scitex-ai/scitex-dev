---
description: |
  [TOPIC] 09 audit checklist
  [DETAILS] Source-backed Web API audit and explicit coverage limits.
tags: ['scitex-general-interface-http-api-audit-checklist']
---

# Web API audit checklist

- Identify the leaf source revision and actual Web API implementation, or record
  missing implementation / a justified inapplicability exception.
- Inspect installed SDK provider metadata before invoking `PS-SDK-WEB` through
  `scitex-dev ecosystem audit-project <distribution> --path . --rule PS-SDK-WEB --json`.
- Verify owned descriptors, schemas and handler bindings using the SDK source
  rule; do not import consumer code just to make a static inspection pass.
- Record unsupported declarations and skipped providers as coverage gaps.
- Verify host admission and route mounting separately from source declarations.
- Exercise authorized and denied requests with owned fixtures before claiming
  live behavior. Include dependency errors and cross-tenant isolation.
- Check README, docs and skills against actual commands and response contracts.

There is no `scitex-dev ecosystem audit-http` command. SDK's installed project
rule and hook providers are the current dispatch path. Static success proves
neither runtime availability nor that the native client executed a hook.
