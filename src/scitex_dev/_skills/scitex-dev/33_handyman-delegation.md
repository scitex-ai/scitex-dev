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

Confirming that a dispatched task is actually being worked is covered in
[34_handyman-verification.md](34_handyman-verification.md).

---

How to write the brief itself is covered in
[35_handyman-briefs.md](35_handyman-briefs.md).
Confirming a dispatched task is actually worked is in
[34_handyman-verification.md](34_handyman-verification.md).
