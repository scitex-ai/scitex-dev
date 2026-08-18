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

### 0. VERIFY THE DELEGATE'S REPORT CHANNEL ROUND-TRIPS

**This outranks every other rule here.** Not "the agent started". Not "the
send returned 200". **A → B → A, observed.**

A delegate you cannot hear is not delegation, it is discarding work — and it
fails silently, looking exactly like a handyman with nothing to say.

The evidence inverts what the rest of this document assumes. Every other rule
below treats the DELEGATE as the weak link and the brief as the compensation.
Measured 2026-08-18, a qwen handyman produced this unprompted, four hours
before any of us wrote a brief:

> "The card store in this project dir is a file literally named
> `${SCITEX_CARDS_DB}` (unexpanded env placeholder) … any agent resolving a
> different path would silently fork the board."
>
> "CAUTION: I did NOT redirect the store to 'fix' it — pointing it at a fresh
> target is exactly how the board was destroyed on 2026-07-19. Left to you."

That is: found the defect, found the obvious fix, evaluated the fix against a
dated prior incident, judged it more dangerous than the bug, declined to act,
escalated. Better judgement than "do not touch what you were not asked to
touch" — it is the reasoning *behind* that rule, derived independently.

**Both reports went into the broken store they were about. Nobody read them.
The escalation was swallowed by its own subject.**

The weak link was not the delegate. It was the channel we never checked.

Three mechanical gaps, all producing the same silence, all present at dispatch:

| gap | effect |
| --- | --- |
| telegrammer MCP not wired in (`mcp doctor` shows only sac) | cannot reach the operator at all |
| config DSN has no password → `fe_sendauth: no password supplied` | Postgres unreachable from inside |
| `notifyd` not running (no pidfile) | push down, pull only |

This is the constitution's "confirm arrival, not dispatch" applied to the
delegation loop, and "a check whose failure nothing reads is not a check"
applied to a REPORT rather than to a gate. Both rules existed. Neither was
applied to the rail the handymen report on, because we were busy writing rules
about their prompts.


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

## Choose the rail before you write the brief

The fleet has **two delivery rails with different guarantees**, and conflating
them is what makes a lost task feel like a bug. sac, who owns the surface,
2026-08-18:

| rail | mechanism | guarantee |
| --- | --- | --- |
| **turn** | `sac agents send` → keystrokes typed into a tmux pane | **EPHEMERAL.** Dies with the session. No queue, no spool, no ack, no redelivery. |
| **card** | scitex-cards inbox / notifications | **DURABLE.** Unseen until explicitly confirmed; anything unacked is REDELIVERED on the next poll. |

A turn is not a message in a queue — it is characters in a running process's
terminal buffer. Kill the session and it is gone in the same sense a
half-typed shell command is gone. That is not a missing feature; adding
durability there means building a work queue that does not exist.

**So: if the work must survive a restart, SEND IT AS A CARD, NOT A TURN.**
A card assigned to a handyman is still there after any number of restarts.
Use a turn for "do this now, I am watching".

This makes restart-awareness a *tool choice*, not a defensive workaround.

### Announce a restart before you take it

Measured 2026-08-18: eight handymen were restarted while a peer had live work
dispatched into one of them. The restart was legitimate and directed, and it
was announced on no channel a delegator reads. Ordering the restarts so the
mid-task agent went last protected nothing — **a restart destroys an in-flight
turn regardless of position.**

If you restart agents, say so where delegators will see it.

---

## Verifying that work is actually happening

**Do not trust the monitoring surfaces. Read the raw pane.** Operator,
2026-08-18: 「監視ツールの出力を盲目的に信用しないで生の tmux のスナップ
ショットとかを見て判断してください」.

Measured the same night. For one dispatched task, every surface was useless:

```
sac agents list    status: running, pid: 0, heartbeat: None
sac agents tail    "No transcript at .../session.jsonl"
agent_send         404
```

One command answered it:

```bash
ssh <host> 'tmux capture-pane -p -S -400 -t tui-<agent>'
```

```
✽ Architecting… (27m 14s · ↓ 9.4k tokens)
  qwen38-27b | ctx:50%
```

Alive, busy — and working on something else entirely.

### Capture deep, not just the bottom

The operator warned that a short capture can miss it, and that is right here:
the identifying lines (model, context %, elapsed) are at the BOTTOM, but the
actual work was hundreds of lines up. `-S -400` at minimum.

### Check the session is older than your dispatch

```bash
ssh <host> 'tmux list-sessions'
```

Dispatch was 02:27. `tui-handyman-c03-01` was **created 02:37:50** — ten
minutes later. The session that received the message no longer existed.

**A restart silently discards a dispatched task and nothing reports it.** The
send returns success; the registry says `running` (true, of the NEW session);
no surface distinguishes *queued* from *being worked* from *died with a
session ten minutes ago*. If the session is younger than your message, your
message is gone — re-send rather than wait.

### A dispatched task is not an accepted task

Require the ACK, and then confirm the ACK arrived **by pane** — the ACK itself
can die with the session.

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
