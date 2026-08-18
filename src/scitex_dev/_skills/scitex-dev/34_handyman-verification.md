---
description: |
  [TOPIC] Handyman Verification
  [DETAILS] DRAFT (2026-08-18) — how to confirm a delegated task is actually being worked. Monitoring surfaces lie: `status: running` observed with pid 0, no heartbeat, no transcript. Read the raw tmux pane with deep scrollback, and check the session is older than your dispatch. Companion to 33_handyman-delegation.md.
tags: [scitex-dev-handyman-verification]
---

# Verifying handyman work

Companion to [33_handyman-delegation.md](33_handyman-delegation.md), which
covers choosing the rail and writing the brief. This file covers confirming
that work is happening at all.

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
