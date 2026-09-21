# ADR-0014 — Access primitive v1: `check()` and `accessible()` in `scitex_dev.access`

**Status:** Accepted (v1: pure core, no persistence)
**Owner:** scitex-dev (core); scitex-app (Django adapter and re-export)
**Implemented by:** scitex-hub, on operator authorisation (2026-09-14)
**Card:** `sdk-authz-can-primitive-for-per-user-app-content-20260914`
(decisive comments: c_b191069828e9 terms, c_d66d1e9df75e operator decisions,
c_2b4624db946f and c_5325aa29f959 feedback envelope, c_0c3e1442ddd2 "everyone is
treated the same")
**Spec:** `src/scitex_dev/access/spec/reasons.yaml` +
`spec/schema/access-decision.schema.json`
**Builds on:** `scitex_dev.scope` (Role, Visibility, `effective_role`),
`scitex_dev.status` (Check, Verdict, exchange id; ADR-0007, ADR-0010),
`scitex_dev.ci` exit codes 10/11

## Context

The operator: every app is visible to everyone; each app's *content* (Cards,
Agents, Writer manuscripts, FigRecipe figures, Scholar libraries, Stats
analyses) shows only what belongs to, or is shared with, the requesting user.
That decision must come from one primitive, not per-app code. A survey found at
least nine disagreeing authorization implementations in the hub alone, eleven
role vocabularies, and two unused half-primitives (`scitex_dev.scope`,
`scitex_app.authz`). The drift between two of them is how the operator's own
account lost the Cards tile.

## Decision

### Terms (one per concept)

| term | meaning |
|---|---|
| principal | `user:<username>`, `org:<id>`, `agent:<owner>/<name>`, or `anonymous` |
| resource | one piece of content: kind + canonical path + owner + visibility + parent |
| kind | a registered resource type (`cards.card`), with a path prefix and action → role |
| role | `read < write < admin` (scope's; Gitea-compatible) |
| action | a verb a kind declares (`view`, `edit`, `share`) mapped to a role |
| grant | principal holds role on a resource; a `default` grant flows to children |
| membership | principal belongs to an org, capped at a role |
| visibility | `private` (default) or `public` |
| decision | the `AccessDecision` record (spec `scitex-access/1`) |

### Operator decisions (c_d66d1e9df75e, c_0c3e1442ddd2)

1. Roles are read/write/admin. rwx exists only as the OS mirror.
2. Default visibility is private.
3. Agents act through explicit delegation grants. An agent's effective role is
   `min(its grant, its owner's role)`: the agent ceiling.
4. The principal id is the username, which is immutable and never reused.
5. No implicit staff bypass. Instance administration is an org membership plus
   an ordinary grant, and the operator is evaluated like every customer.

### API

```python
check(principal, action, resource, *, grants, memberships, kinds=None) -> AccessDecision
accessible(principal, action, kind, *, grants, memberships, kinds=None) -> AccessFilter
require(...)            # check() that raises AccessDenied / AccessUnresolved
decide_missing(...)     # a resource the adapter could not find; renders like a private one
decide_unresolved(...)  # an adapter could not reach the enforcer or identity
```

Rules, and the reason chosen when several allow, in order: `owner` (admin),
`grant`, `inherited` (a default grant on the parent), `org` (via membership,
capped by the membership role), `public` (read for everyone, including
anonymous). A denial is `not-visible` when the principal holds no role on a
private resource, `role-too-low` when it holds a weaker role, `agent-ceiling` /
`owner-has-no-role` for a capped agent, and `not-signed-in` for anonymous. A kind
nobody registers is `unresolved/kind-unregistered`, so it fails closed.

`accessible()` returns a backend-neutral `AccessFilter` (owner ids, granted
resource refs, parent refs with default grants, a public flag, and for agents
the owner's filter as a ceiling). Adapters translate it once into a Django `Q`
or a store query. `scitex_dev.access.testing` is the conformance suite: on
random fixtures, every resource `check()` allows must be selected and nothing
else.

### Feedback envelope

The record wraps the status types instead of extending them:

```json
{"spec": "scitex-access/1", "exchange_id": "xch_…",
 "decision": {"kind": "denied", "role": "read", "required_role": "write"},
 "reason": "role-too-low",
 "check": {"name": "access", "ok": false, "detail": "…", "hint": "…"},
 "request": {"principal": "user:bob", "action": "edit", "resource": "demo.doc:/…"}}
```

`check.ok`, the HTTP status and the exit code are derived from (kind, reason)
through `reasons.yaml` and never serialised. The reasons list is closed and
append-only, and a drift test pins code to YAML.

| surface | mapping |
|---|---|
| Python | `AccessDenied(PermissionError)`, `AccessUnresolved(RuntimeError)`, `AccessConfigError(ValueError)` |
| CLI | `<pkg> dev access check …` exits 0 allowed, 10 denied / not signed in / not entitled, 11 unresolved (never 1/2) |
| HTTP | 200; 404 `not-visible` (identical to a missing resource); 403; 401 `not-signed-in`; 503 unreachable; 500 `kind-unregistered` |

### Registration and CLI

Kinds register through the `scitex_dev.access.kinds` entry point (a callable
returning `list[KindSpec]`). One name registered twice with different rules is
refused. A leaf mounts the CLI the way it mounts `secret`:
`register_access_group(dev, pkg="<dist>")`. v1 reads grants from a JSON fixture
(`--fixture`) because nothing is persisted yet.

## Rejected: Postgres Row-Level Security (v1)

RLS was evaluated as defence in depth and rejected for v1:

- the hub runs PgBouncer in transaction mode, so a per-session GUC carrying the
  asker is unreliable without `ATOMIC_REQUESTS` and explicit transactions;
- it would be a second evaluator of the same rules, which can drift from
  `check()`;
- table owners bypass RLS unless it is forced;
- scitex-cards ADR-0017 (`docs/adr/0017-identity-tenancy-and-file-ssot.md`, D0
  "a tenant is a store, not a row") already records "No tenant_id column on
  tasks. No RLS. No session GUC. No DB-role split", because RLS-filtered reads
  blind the board-wipe guard.

Instead, isolation comes from owner/grant evaluation (`check` / `accessible`),
NOT NULL owner columns on content tables, a restricted grant-writer DB role,
and a per-adopter zero-foreign-rows test. A separate per-organisation store
remains a contractual option only.

## Consequences

v1 ships pure-core `check()` / `accessible()` with owner/grant
evaluation, NOT NULL owner columns, a restricted grant-writer role, and
a per-adopter zero-foreign-rows test. RLS stays rejected for v1. The
per-adopter follow-ups are owned where they are listed — `Consequences
and v2` below.

## Consequences and v2

Left for v2, each owned by its adopter:

- scitex-app: Django adapter (`AccessFilter` → `Q`, `AccessScopedManager`) and
  the re-export through `scitex_sdk.app`; rename `authz.Verdict` → `Decision`
  with an alias.
- scitex-hub: `apps/infra/access_app` Grant model (replacing the dead
  `permissions_app`), a data migration from `ProjectMembership.permission_level`,
  and `/api/access/*`.
- scitex-cards, sac, writer, figrecipe, scholar, stats: register kinds, store
  kinds with two-step `accessible()`, and run `scitex_dev.access.testing`.
- Recording and notification: `access_events` in `scitex_dev.store`, the
  `scitex_dev.access.feedback` entry point, retention, and the federated
  `scitex-dev ecosystem dev access`.
- Grant mutation verbs (`access grant|revoke|visibility`) once grants persist.
