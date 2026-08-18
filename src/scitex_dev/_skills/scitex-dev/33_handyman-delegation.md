---
description: |
  [TOPIC] Handyman Delegation
  [DETAILS] DRAFT (2026-08-18) — how to delegate work to handymen, which cost no Anthropic quota. Written from ZERO completed delegations: the rules are failure modes predicted or hit while writing briefs, not lessons from finished work. Covers pre-dispatch checks (the worker's host must have the repo), brief design (mechanical steps, an explicit "I cannot" branch, positive controls, numbers that must match and must not be matched), and tool traps that read as clean zeros. Correct from real outcomes.
tags: [scitex-dev-handyman-delegation]
---

# Delegating to handymen

Handymen run a locally-served model, so their work costs no Anthropic quota.
Operator, 2026-08-18: 「ハンディマンが空いてる時はガンガン仕事を振ってやらせて
ください。それが全体のクオータ削減に繋がります。ハンディマンとの協同の
ベストプラクティスをみんなで作り上げてください」.

**STATUS: DRAFT, LARGELY UNTESTED.** Written 2026-08-18 from three agents'
first attempts. At the time of writing, **zero delegations had completed** —
one was dispatched and never confirmed received, two were still running. The
rules below are the failure modes we predicted or hit while *writing* briefs,
not lessons from finished work. Six rules from one night and no completed
delegation would be exactly the confident-untested shape this fleet keeps
catching; treat it accordingly and correct it from real outcomes.

---

## Before you dispatch

### The worker's host must have the repo

Measured 2026-08-18: `scitex-compute-03` runs **eight handymen** and has **no
`scitex-dev` checkout** — no venv, no `~/proj/scitex-dev`, bare system Python.
A task sent there was undoable before it was written.

Check first:

```bash
ssh <host> 'ls -d ~/proj/<repo> 2>/dev/null || echo NO-CHECKOUT'
```

This puts host provisioning (repo → deployer → host) upstream of the whole
delegation strategy: you cannot delegate against a repo the worker cannot see.

### Reaching them at all

Cross-host `agent_send` currently fails. An agent started with
`ssh <host> 'sac agents start <name>'` propagates no peer-visible `a2a_port`,
so the caller's registry row is empty and routing 502s — while the sidecar is
bound and healthy. **The transport works; the directory is empty.**

Workaround until sac's durable fix lands (they are doing pull-on-miss rather
than propagate-on-start, because propagation only ever fixes agents started
*after* it ships):

```bash
ssh <host> 'sac agents send <name> "<prompt>"'
```

Resolution on the target host is local and has the full fallback chain.

### Finding them

`sac agents list --capability handyman` returns **0** while eight are running.
The filter reads `labels.capabilities` (which holds verbs — `edit, refactor,
read, test…`); "handyman" lives in `labels.purpose`. Until fixed, list
unfiltered on the target host.

---

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

## Known capacity

As of 2026-08-18, **do not quote a fleet total.** Measured: 8 handymen on
compute-03. Reported but unqueryable: 4 on `scitex-laptop-01`, a host absent
from the registry entirely. Three hosts did not answer. Cross-host a2a is
broken, so reachable-from-elsewhere capacity is smaller than running capacity.

`status: running` on a handyman row has been observed with `pid: 0`, no
heartbeat and no session transcript — a stored label, not a measurement. Do not
read it as evidence the worker is alive.

---

## Contributors

scitex-dev, scitex-agent-container, scitex-cards — 2026-08-18. Correct this
file from real outcomes rather than adding rules to it from reasoning.
