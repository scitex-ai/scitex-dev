---
description: |
  [TOPIC] Two-Tier Master-Host Credential Rotation — one refresher per account, fleet-wide
  [DETAILS] OAuth refresh_tokens rotate (single-use); when >1 host refreshes the SAME account, whichever refreshes first invalidates the others → quota stall. Fix: a MASTER host (sole refresher per account) mints a short-lived ACCESS-ONLY artifact (refreshToken STRUCTURALLY ABSENT) that CONSUMER hosts PULL read-only and literally cannot refresh. Auditable invariant: exactly ONE active accounts-refresh timer per account, fleet-wide. Account declared `pooled` (healthy+lowest-quota selector) or `exclusive:<label>` (strict, no substitute). Transport = listen-bearer over the mesh (mesh-consumer #3), SSH-fanout fallback for no-listen hosts. Mint-on-pull cadence; fail-loud + starvation card on degrade. sac owns the mechanism (`mint-token`/`pull-token`); scitex-dev owns this convention. Sibling to the multi-host-connect mesh standard.
tags: [scitex-general-ecosystem-credential-rotation-two-tier]
---

# Two-Tier Master-Host Credential Rotation

OAuth `refresh_token`s are **single-use / rotating**: each refresh mints a new
access token AND a new refresh token, invalidating the old one. So when **more
than one host refreshes the SAME account**, whichever refreshes first
invalidates the other host's refresh token → that host's credential dies and its
quota stalls. Real incident: one account dual-homed on WSL (`ywata-note-win`) +
Spartan, both running a refresh timer, constant mutual invalidation. The fix
mirrors scitex-todo's master/consumer SSoT and the fleet multi-host-connect
mesh: **one writer, many read-only consumers.**

## 1. The two-tier model

- **MASTER host** (`ywata-note-win`) — the **SOLE refresher per account**,
  fleet-wide. It refreshes, mints access-only artifacts, and selects accounts.
- **CONSUMER / compute hosts** — **READ-ONLY**. They PULL a short-lived
  access-only artifact from the master and **NEVER refresh** — they
  *structurally cannot* (§3).
- **INVARIANT (auditable):** exactly **ONE** active accounts-refresh timer per
  account, fleet-wide = the master. Peer refreshers MUST be disabled. A
  fleet-audit flags any account with >1 active refresh timer — state it as a
  checkable rule, the same shape as an ecosystem linter rule:
  > **CR-001** — per account, exactly one host runs an `accounts refresh`
  > timer. `>1` is a violation (mutual-invalidation risk); `0` on the master
  > is a violation (no refresher).

## 2. Account declaration (`spec.claude.account`)

| Value | Meaning | Selection policy |
|---|---|---|
| `pooled` | master assigns any healthy account | pick **healthy AND lowest-quota**, **freshness-aware** — never an expired account |
| `exclusive:<label>` | a dedicated, non-conflicting account (e.g. Spartan) | **STRICT**: if `<label>` is unhealthy, mint **FAILS** (`requested exclusive account <label> unhealthy`) — **never substitutes** |

**Capacity tradeoff — an operator PROVISIONING decision.** `exclusive:<label>`
removes that account from the host rotation pool; with `N` accounts it shrinks
host capacity to `N-1`. Provision a **dedicated compute account** rather than
starving the pool.

## 3. The access-only artifact (the structural race-guard)

Master command `sac accounts mint-token --account <label>` emits ONE JSON
envelope on stdout:

```json
{ "artifact": {"claudeAiOauth": {"accessToken":"<...>","expiresAt":<epoch_ms>,
    "scopes":["user:inference","user:profile"]}},
  "meta": {"account":"<label>","master_host":"<host>","minted_at":<epoch_ms>,
    "expires_at":<epoch_ms>,"artifact":"access-only","artifact_version":1} }
```

- **`refreshToken` is STRUCTURALLY ABSENT** from `artifact.claudeAiOauth` → a
  claude-code consumer **literally CANNOT refresh** (it fails-loud at expiry
  rather than silently rotating). This is how "consumers never refresh" is
  enforced: **by mechanism, not by trust.** The policy is the data shape.
- **Split-write** (consumer side): `artifact` → `~/.claude/.credentials.json`,
  `meta` → `~/.claude/.credentials.meta.json`. The meta lives OUTSIDE the oauth
  envelope so claude-code's parser is not confused by extra keys. Both writes
  are **atomic (temp + rename)**; timestamps are **epoch-MILLISECONDS**.
- **Security:** the master reads the `refresh_token` internally to mint, but it
  **NEVER leaves the master** — never in output, never in logs. Only the access
  token crosses the wire, by design.

## 4. Transport & cadence

- **Transport:** **listen-bearer over the fleet multi-host mesh** where the
  consumer host runs a listen — this is **mesh-consumer #3** of the
  multi-host-connect standard. **SSH-fanout to the master** is the FALLBACK for
  **no-listen hosts** (Spartan's ephemeral capsules are the mesh's
  graceful-degrade case).
- **Cadence — MINT-ON-PULL:** the pull triggers the master to strip-and-return
  the **CURRENT** `accessToken` (freshest possible — never a cached artifact).
  The consumer pulls at **capsule-START**, then **RE-PULLS** with retry-backoff
  once `(expires_at - now) < 1h`, retrying until it gets a fresh token OR the
  token actually expires. The master ALSO **push-on-refresh** to listen-capable
  consumers (event-driven). Token life ~8h.

## 5. Degrade — fail-loud, never silent

Master unreachable at re-pull → keep the **last-good token until expiry**, then
**FAIL-LOUD and EMIT a signal**: an a2a / board **starvation card**:
> `compute host <h> credential-starved: account <label> expired <ts>, master unreachable`

No silent failure — a starved capsule is **visible to the operator**.

## 6. Ownership boundary

- **sac (scitex-agent-container) owns the MECHANISM:** `mint-token`,
  `pull-token`, the mesh push/pull rail, the account store + selector.
- **scitex-dev owns THIS convention** (this skill). Sibling to the fleet
  **multi-host-connect** standard (the mesh); credential-distribution is
  **mesh-consumer #3**. Constitution-referenceable.

## 7. Related

- Multi-host-connect convention (the mesh) — this is its credential-distribution
  consumer (#3); listen-bearer primary, SSH-fanout fallback.
- [13_runtime-state-db-layout.md](13_runtime-state-db-layout.md) /
  [12_local-state-resolution.md](12_local-state-resolution.md) — the
  `~/.claude/.credentials{,.meta}.json` files are **user-canonical runtime
  state** written by the consumer; same atomic-write / user-scope discipline.
- scitex-todo's master/consumer two-tier SSoT — the **pattern origin** (one
  writer, many read-only pullers).
- [15_credential-rotation-spartan-pull.md](15_credential-rotation-spartan-pull.md)
  — the Spartan consumer deliverable (`pull-token` contract, clew receive side).
