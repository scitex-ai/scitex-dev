---
name: quality-guards
description: Quality enforcement rules — no fallbacks, no false positives, no patch work, script everything. Use when reviewing code, verifying fixes, or ensuring code quality.
---

# Quality Guards

## No Fallbacks
- Never allow silent failures
- Never implement fallbacks unless user explicitly requests
- For user-confirmed fallbacks, comment it in source code
- Red cases are useful — do not hide them
- Not working must be not working. Not complete must be not complete.

## No False Positives
Never claim "fixed", "working", or "done" without ALL verification steps:

1. **Log-level** — read actual logs, check for errors/warnings
2. **Tests** — run relevant tests, read PASS/FAIL for each
3. **Visual** — open page with playwright-cli, take screenshot, compare layout
4. **Functional** — test exact user scenario on actual environment

Anti-patterns: trusting HTTP status codes, saying "should be working" without proof, declaring "code loaded" as "feature working".

## No Patch Work
- Find root causes, not surface fixes
- Don't apply band-aids that mask the real problem
- If a fix feels hacky, pause and find the elegant solution

## No Long-Term Memory
The user has deficits in long-term memory. Script everything:
- Minimize manual steps in installation
- Makefile as thin dispatcher, delegate to downstream scripts
- `make status` is the reliable information device
- Switch environments via `.env.{dev,prod}` and `./deployment` scripts

## Detailed References
- [No fallbacks rules](no-fallbacks.md)
- [No false positives verification checklist](no-false-positives.md)
- [No long-term memory rules](no-long-term-memory.md)
