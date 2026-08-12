---
description: |
  [TOPIC] Credential Rotation — Spartan Replica Pull Contract
  [DETAILS] The replica/compute side of the two-tier credential model (14). Spartan is a no-persistent-listen host → PULL model: `sac accounts pull-token --account <label|auto> --out ~/.claude/.credentials.json [--master ywata-note-win]` fetches the access-only envelope via SSH-fanout to the primary, split-writes the oauth artifact + `.credentials.meta.json` atomically, and prints `{account, expires_at}` for the caller's re-pull scheduler. clew wires the receive side. sac owns the command (mechanism); this documents the CONTRACT. Pull at capsule-start, re-pull with backoff under 1h-to-expiry, fail-loud + starvation card if the primary is unreachable at expiry. NOTE: the option is spelled `--master` because that is the published flag name; renaming it is sac's migration, not a doc edit (§1).
tags: [scitex-general-ecosystem-credential-rotation-spartan-pull]
---

# Credential Rotation — Spartan Replica Pull Contract

The **replica side** of the two-tier model
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

> **`--master` is the published flag name — do NOT rewrite it to `--primary`
> in prose.** The fleet naming convention
> ([25_naming-conventions.md](../../scitex-dev/25_naming-conventions.md)) puts
> the credentials domain on **primary/replica**, and the ROLE this flag names
> is now called the primary throughout this leaf. The FLAG keeps its spelling
> because a published CLI token is a **migration, not a rename**: a runbook,
> a capsule bootstrap or a clew invocation that passes `--master` must keep
> working. Renaming it here while the command still parses `--master` would
> make this document lie, which is worse than an out-of-date word.
>
> **Migration path (sac's change, not scitex-dev's).** sac owns `pull-token`
> (14 §6), so the alias lands there:
>
> 1. sac adds `--primary` as the canonical option and keeps `--master` as a
>    hidden, still-functional alias (`click.option("--primary", "--master", …)`).
> 2. Both spellings work for at least one release; `--master` warns once on use.
> 3. When no caller passes `--master`, sac removes it and THIS block is
>    deleted, leaving `--primary` in the snippet above.
>
> Step 1 has not happened yet — as of 2026-08-11 `pull-token` is unimplemented
> in sac (`_account/mint_token.py` records it as "a SEPARATE later change") and
> no `--master` option string exists in the sac tree. That makes this the
> cheapest possible moment to land the alias, and it is tracked as a card
> against sac rather than actioned here: scitex-dev does not edit another
> package's CLI.

- `--account auto` → the primary's **pooled** selector picks a healthy,
  lowest-quota, non-expired account. `--account <label>` → **exclusive** request
  (strict — mint FAILS if `<label>` is unhealthy; never substitutes). Both
  policies are decided **on the primary** (14 §2) — the replica only asks.
- `--master` defaults to the fleet primary (`ywata-note-win`); explicit override
  for testing / a relocated primary.

## 2. What it does (the contract)

1. **Fetch** the access-only envelope from the primary via **SSH-fanout**
   (Spartan is no-listen). The pull triggers **mint-on-pull** — the primary
   strips its current refresh token and returns the freshest `accessToken`
   (14 §3–4). The `refreshToken` is structurally absent from the envelope.
2. **Split-write, atomically (temp + rename):**
   - `artifact` → `~/.claude/.credentials.json` (the oauth envelope
     claude-code reads),
   - `meta` → `~/.claude/.credentials.meta.json` (OUT of the oauth envelope,
     so claude-code's parser is not confused). Its `master_host` key keeps that
     spelling for the same contract reason as the flag — see 14 §3.
3. **Print** `{account, expires_at}` (epoch-**milliseconds**) on stdout for the
   **caller's re-pull scheduler**.

## 3. Re-pull scheduling (caller side)

- **Pull at capsule-START** (before the agent session boots).
- **RE-PULL** with retry-backoff once `(expires_at - now) < 1h`, retrying until
  a fresh token arrives OR the current token actually expires. Read `expires_at`
  from the `pull-token` stdout (or from `.credentials.meta.json`).
- **Degrade — fail-loud:** if the primary is unreachable at re-pull, keep the
  **last-good token until expiry**, then **FAIL-LOUD** and emit the a2a / board
  **starvation card** (14 §5):
  > `compute host <h> credential-starved: account <label> expired <ts>, primary unreachable`

  Never silently continue with an expired token — a starved capsule must be
  visible to the operator.

## 4. Receive-side wiring

- **clew** wires the receive side against this contract — it invokes
  `pull-token` at capsule-start and owns the re-pull scheduler + starvation-card
  emission on its host.
- Any new compute-host replica copies this: pull at start, schedule the re-pull
  off the printed `expires_at`, fail-loud on starvation.

## 5. Related

- [14_credential-rotation-two-tier.md](14_credential-rotation-two-tier.md) — the
  model, the access-only artifact schema, the auditable one-refresher invariant,
  and the ownership boundary. Read it first; this is its replica deliverable.
- Multi-host-connect convention (the mesh) — SSH-fanout is the mesh fallback for
  no-listen hosts; this pull path is that fallback in action.
- [25_naming-conventions.md](../../scitex-dev/25_naming-conventions.md) — the
  fleet naming table, and the migration-not-rename rule the `--master` flag
  above is held to.
