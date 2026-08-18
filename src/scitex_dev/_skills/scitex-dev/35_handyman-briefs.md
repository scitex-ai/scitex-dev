---
description: |
  [TOPIC] Handyman Briefs
  [DETAILS] DRAFT (2026-08-18) — how to write a task brief for a handyman: mechanical steps rather than goals, an explicit "I cannot" branch, a positive control with a stop condition, numbers that must match and must not be matched, and demanding the raw value rather than a verdict. Includes tool traps that read as clean zeros. Companion to 33_handyman-delegation.md.
tags: [scitex-dev-handyman-briefs]
---

# Writing a handyman brief

Companion to [33_handyman-delegation.md](33_handyman-delegation.md) (rails and
pre-dispatch checks) and [34_handyman-verification.md](34_handyman-verification.md)
(confirming work happens).

## Writing the brief

### 1. Mechanical steps, not goals

"Read this file, answer these nine questions YES/NO/UNCLEAR with a quoted
line" — not "figure out what the search does". A weaker model given a goal
invents a plausible path; given steps, it executes them.

### 2. Make "I cannot" an explicit branch

State it: *if you have no checkout, say so and STOP — do not clone.*
Without that branch, "could not" and "never received it" look identical, and
you cannot tell a failed dispatch from a refused one.

Likewise allow **UNCLEAR** as an answer, in those words: *"Use UNCLEAR freely.
A wrong label is worse than an honest UNCLEAR."* Invention in a delegated
*reading* is the most expensive failure available, because it arrives looking
like a finding.

### 3. Require an ACK before work starts

One line, before any work: can you see the repo, yes or no. Turns silence into
a diagnosable answer.

### 4. Carry a positive control with a stop condition

Include one command whose answer you already know, and write: *if it returns
zero, say so and STOP — do not continue and do not report findings.*

A delegate cannot notice its own broken search from inside. An instrument that
has never returned a known answer is not a measurement.

### 5. Give numbers that must match — and forbid matching them

> "79 test functions before, 79 after. If they differ, STOP and tell me the
> difference. Do NOT add or delete a test to make them match."

> "I expect roughly 8 files. If you get a very different number, that is
> interesting — report the number you actually got, do not adjust it to match
> my expectation."

An expectation alone invites confirmation. An expectation **plus** the
instruction not to match it turns the number into a calibration signal: a
sharp divergence means either your figure is stale or their search is broken,
and both are worth knowing.

A worker optimising for a green check will otherwise make the check green.

### 6. Demand the raw value, never a verdict

> "Report the EXIT CODE, not the summary line. Do not interpret it."

`scitex-dev`'s suite prints `N passed` and can still exit non-zero, because a
guard refuses partial runs. A delegate that summarises will report success.

### 7. Require a "what I could not determine" section

Rated by all three contributors as the highest-value line in a brief. The two
best delegate outcomes observed so far were exactly this behaviour: a worker
reporting that its own monitor had lied to it, and one writing "I have not run
the negative experiment" rather than presenting a code reading as a
demonstration.

### 8. Report what you actually saw

Paste real output. If a command returned nothing, write "returned nothing". If
it errored, paste the error — **an error is a useful result; an invented one is
not.**

---

## Tool traps to write INTO the brief

Do not trust the delegate to know these; state the correct invocation.

| trap | consequence |
| --- | --- |
| `rg --include` | `--include` is grep's flag. `rg` errors, and the error piped into a count reads as a clean **zero** |
| bare `rg` / `grep` in some agent shells | shimmed; use `/usr/bin/<cmd>` when parsing output |
| `cmd \| tail -N` for a verdict | you read *tail's* exit status, always 0 |
| `/usr/bin/rg` inside a COMMITTED test | the opposite constraint — CI hosts may not have ripgrep |

That last row is a genuine conflict: interactive-shell guidance and
committed-artifact guidance point opposite ways. Both are right in their own
context and they do not transfer.

---
