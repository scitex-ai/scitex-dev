---
description: |
  [TOPIC] Credential Rotation — Spartan Consumer Pull Contract
  [DETAILS] The consumer/compute side of the two-tier credential model (14). Spartan is a no-persistent-listen host → PULL model: `sac accounts pull-token --account <label|auto> --out ~/.claude/.credentials.json [--master ywata-note-win]` fetches the access-only envelope via SSH-fanout to the master, split-writes the oauth artifact + `.credentials.meta.json` atomically, and prints `{account, expires_at}` for the caller's re-pull scheduler. clew wires the receive side. sac owns the command (mechanism); this documents the CONTRACT. Pull at capsule-start, re-pull with backoff under 1h-to-expiry, fail-loud + starvation card if the master is unreachable at expiry.
tags: [scitex-general-ecosystem-credential-rotation-spartan-pull]
---

# Credential Rotation — Spartan Consumer Pull Contract

The **consumer side** of the two-tier model
([14_credential-rotation-two-tier.md](14_credential-rotation-two-tier.md)).
Spartan has **no persistent listen** → it uses the **PULL model** (the mesh's
graceful-degrade / SSH-fanout case, §4 of 14). This leaf pins the pull command
contract so any compute-host receive side (clew, a bare capsule) implements it
identically.

> **Note:** `pull-token` is being built in **scitex-agent-container** (sac owns
> the mechanism). This skill documents the **contract / convention**, with sac
> as the mechanism owner.

## 1. The pull command

```bash
sac accounts pull-token \
  --account <label|auto> \
  --out ~/.claude/.credentials.json \
  [--master ywata-note-win]
```

- `--account auto` → the master's **pooled** selector picks a healthy,
  lowest-quota, non-expired account. `--account <label>` → **exclusive** request
  (strict — mint FAILS if `<label>` is unhealthy; never substitutes). Both
  policies are decided **on the master** (14 §2) — the consumer only asks.
- `--master` defaults to the fleet master (`ywata-note-win`); explicit override
  for testing / a relocated master.

## 2. What it does (the contract)

1. **Fetch** the access-only envelope from the master via **SSH-fanout**
   (Spartan is no-listen). The pull triggers **mint-on-pull** — the master
   strips its current refresh token and returns the freshest `accessToken`
   (14 §3–4). The `refreshToken` is structurally absent from the envelope.
2. **Split-write, atomically (temp + rename):**
   - `artifact` → `~/.claude/.credentials.json` (the oauth envelope
     claude-code reads),
   - `meta` → `~/.claude/.credentials.meta.json` (OUT of the oauth envelope,
     so claude-code's parser is not confused).
3. **Print** `{account, expires_at}` (epoch-**milliseconds**) on stdout for the
   **caller's re-pull scheduler**.

## 3. Re-pull scheduling (caller side)

- **Pull at capsule-START** (before the agent session boots).
- **RE-PULL** with retry-backoff once `(expires_at - now) < 1h`, retrying until
  a fresh token arrives OR the current token actually expires. Read `expires_at`
  from the `pull-token` stdout (or from `.credentials.meta.json`).
- **Degrade — fail-loud:** if the master is unreachable at re-pull, keep the
  **last-good token until expiry**, then **FAIL-LOUD** and emit the a2a / board
  **starvation card** (14 §5):
  > `compute host <h> credential-starved: account <label> expired <ts>, master unreachable`

  Never silently continue with an expired token — a starved capsule must be
  visible to the operator.

## 4. Receive-side wiring

- **clew** wires the receive side against this contract — it invokes
  `pull-token` at capsule-start and owns the re-pull scheduler + starvation-card
  emission on its host.
- Any new compute-host consumer copies this: pull at start, schedule the re-pull
  off the printed `expires_at`, fail-loud on starvation.

## 5. Related

- [14_credential-rotation-two-tier.md](14_credential-rotation-two-tier.md) — the
  model, the access-only artifact schema, the auditable one-refresher invariant,
  and the ownership boundary. Read it first; this is its consumer deliverable.
- Multi-host-connect convention (the mesh) — SSH-fanout is the mesh fallback for
  no-listen hosts; this pull path is that fallback in action.
