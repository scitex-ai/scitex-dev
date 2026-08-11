---
name: scitex-naming-conventions
description: Fleet-wide role/name pair table — primary/replica, controller/worker, node/origin, service/timer/cron — decided by the operator 2026-08-11; use these words, not their synonyms
---

# SciTeX naming conventions (operator-decided, 2026-08-11)

One table, so the same concept never ships under two names again. When writing
code, cards, docs, or messages, use the LEFT column's pair for that domain —
the "banned synonyms" column lists words that have already caused drift.

| Domain | Use | Meaning | Banned synonyms |
|---|---|---|---|
| Credentials | **primary / replica** | `primary` = the host whose store is the origin of a credential (scitex-nas-03 for Claude OAuth); `replica` = a host that receives a materialized copy | master/slave, canonical/copy, source/dest |
| Roles (agents, processes) | **controller / worker** | `controller` supervises and dispatches; `worker` executes | master/slave, lead/follower (`lead` survives only as the existing agent's name) |
| DB replication (`scitex_dev.store`) | **node / origin** | every host is a `node`; a row's `origin` is the node that authored it (HLC tie-breaker). Deliberately NOT primary/replica: the store is multi-writer, no node outranks another | primary/replica (wrong model here), master |
| Job kinds (`JobSpec`) | **service / timer / cron** | `service` = long-running unit; `timer` = periodic systemd unit; `cron` = crontab line. This is the KIND, the CLI group, and the vocabulary — all three | daemon, systemd, periodic (as kind names) |
| Job names | **`scitex-<pkg>-<name>`** | canonical id, hyphens only; a package CLI accepts the local short name and prefixes it | dots (`sac.accounts-refresh`), underscores |
| Job mechanism (internal field only) | systemd / cron / respawn / launchd | HOW a job is delivered on a host; never appears in a CLI group name or a job name | — |

## Why each pair (one line each, so the reasoning survives)

- **primary/replica**: the credential flow is one-directional by design — refresh
  happens only at the primary (the NAS renewal session); a replica that refreshes
  would revoke the primary's token (single-use refresh tokens). The name pair
  encodes the direction.
- **controller/worker**: operator's explicit replacement for master/slave
  (2026-08-11: 「master vs slave は… controller vs. worker にしましょうか」).
- **node/origin**: operator reviewed and accepted (「なるほど、node vs. origin
  ですね」). In the store every host writes; `origin` marks authorship, not rank.
- **service/timer/cron**: these are `scitex_dev.jobs.ALLOWED_KINDS` — the enum,
  the `scitex-<pkg> dev <kind> <verb>` CLI grammar, and the auditor's vocabulary
  (PS-226..229). `kind="systemd"` raises `ValueError`; a CLI group named
  `systemd` is a deprecated alias with `remove_after=2026-10`.

## Provenance

Decided on Telegram 2026-08-11 (operator + sac). Enforced mechanically where
possible: job names/kinds by auditor rules PS-226..229, the CLI grammar by
sac's `dev {service,timer,cron}` groups and `ecosystem dev {service,timer,cron}`
here. The prose pairs (primary/replica, controller/worker, node/origin) are
convention until an auditor rule exists — adding one is fair game.
