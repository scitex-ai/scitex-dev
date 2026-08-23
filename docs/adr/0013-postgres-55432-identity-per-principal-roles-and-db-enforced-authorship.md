# ADR-0013 — Postgres 55432 identity: per-principal roles, DB-enforced authorship, row-level ACL

**Status:** Proposed — design only. **This ADR grants no one permission to apply it.**
**Owner (design):** scitex-dev
**Owner (application):** UNDECIDED — see "Who may apply this"
**Requested by:** operator, 2026-08-23 — "design it; not just permissions —
`scitex_cards` is apparently a shared role. It needs designing from both the
security side and the practical side."
**Consulted:** business (2026-08-23, four written answers; quoted below)
**Related:** ADR-0006 (one store per host, consumed as a primitive) and its
Decision 7, whose reversal to TCP-55432 is the ruling this design implements;
card `dev-adr0006-decision7-reverse-to-tcp-55432-with-acl-20260810`;
card `dev-lost-update-whole-card-writeback-destroys-concurrent-edits-20260810`

---

## 0. How to read the evidence in this document

business asked for this explicitly, and they were right to:

> Please make a column in the design document that separates "this is inferred,
> I did not measure it".
> (「設計文書に『これは推論で、測っていない』と書き分ける欄を作ってください。」)

Every factual claim below is tagged:

- **[M]** — measured on the live cluster on 2026-08-23, with the query or
  command that produced it named. Reproducible.
- **[I]** — inferred. Follows from something measured, but was not itself
  observed. Can be wrong.
- **[U]** — unknown. Named here precisely because leaving it out would make the
  design read as complete when it is not.

The measurement harness is read-only and is recorded in §1. Nothing in this
document was changed on the cluster to produce it.

---

## 1. What was measured

Cluster: PostgreSQL **18.4 (Debian 18.4-1.pgdg13+1)** on port **55432**,
`data_directory = /home/ywatanabe/.scitex/pg/18/main`, reached with the DSN
that `scitex_cards.resolve_store()` returns:
`postgresql://scitex_cards@127.0.0.1:55432/scitex_cards`. **[M]**

### 1.1 The shared role is a superuser, and it is the only login role

```
rolname       | rolsuper | rolcreaterole | rolcreatedb | rolcanlogin | rolbypassrls
scitex_cards  | t        | t             | t           | t           | t
```

`pg_roles` holds **17 rows: 16 built-in `pg_*` roles and `scitex_cards`.** No
other role can log in. **[M]**

So the operator's phrasing — a shared role — is correct and understates it.
It is a shared **superuser**, held by every agent, every package and CI.
`rolbypassrls = t` additionally means this role ignores row-level security,
so the row-level ACL that ADR-0006 Decision 7 calls for **cannot be enforced
against the only principal that exists.** **[M]**

### 1.2 Authorship is a self-declared string with no default and no constraint

Every attribution column in the schema is `text`, nullable, with **no column
default**: `tasks.created_by`, `tasks.agent`, `tasks.assignee`,
`task_comments.author`, `notifications.actor`,
`notifications_quarantine.actor`, `dm_threads.created_by`,
`dm_thread_member_events.actor`. **[M]**

The board currently holds **5,888 tasks across 30+ distinct `created_by`
values** — `scitex-agent-container` 1,477, `scitex-cards` 688, `scitex-hub`
642, `scitex-dev` 501, `ci` 438, `operator` 58, … **and 147 rows where
`created_by` is empty.** **[M]**

Because all 30+ of those principals authenticate as the same role, the
database cannot distinguish them. **Any client holding the DSN can write any
author string, including `operator`.** **[I — follows from 1.1 + the absence of
any default or trigger; I did not attempt a forged write, and will not.]**

The `users` table — the registry that would say which principals exist —
contains **0 rows.** **[M]**

### 1.3 Nothing is auditable, and the audit extension is not merely uninstalled

```
track_commit_timestamp | off   (default)
log_connections        | ''    (default)
log_disconnections     | off   (default)
log_statement          | none  (default)
shared_preload_libraries | ''  (default)
pg_extension           | plpgsql only
```

**[M]**

`pg_available_extensions` offers `pgcrypto` and `sslinfo`. **`pgaudit` is not
in the list at all** — it is not installed on the host, so enabling it is an OS
package installation, not a configuration line. **[M]** business reported
pgaudit as "not enabled"; the stronger and more useful fact is that it is not
*available*, which changes who has to act and how long it takes. **[M]**

business's consequence stands and is the reason this matters:

> What is not enabled cannot be recovered retroactively. Enable it today and
> everything before today is still empty. If audit is the goal, "when did you
> turn it on" becomes the effective start date of the audit.
> (「入っていないものは、後から遡れません。」)

### 1.4 TLS is off, and the overlay is already reachable

```
ssl              | off             (default)
listen_addresses | 127.0.0.1,100.64.0.1   (configuration file)
port             | 55432                  (configuration file)
```

`pg_hba_file_rules`:

| line | type | database | user | address | netmask | method |
|---|---|---|---|---|---|---|
| 121 | local | all | all | | | scram-sha-256 |
| 123 | host | all | all | 127.0.0.1 | /32 | scram-sha-256 |
| 125 | host | all | all | ::1 | /128 | scram-sha-256 |
| 128–130 | replication | all | all | localhost | | scram-sha-256 |
| 132 | host | scitex_cards | scitex_cards | 100.64.0.0 | 255.192.0.0 | scram-sha-256 |

**[M]**

Line 132 is `100.64.0.0/10` — the whole CGNAT range the overlay uses. So
**every node on the overlay can already attempt to authenticate as the shared
superuser**, and the only thing between an overlay node and the cluster is that
role's password. Transport confidentiality is provided by the overlay's own
encryption, **not** by Postgres: `ssl = off`. **[M]**

The operator's condition on the 2026-08-10 reversal was "keys are of course
mandatory" (「はい、もちろん鍵は必須です。」). **That condition is not in effect
today.** **[M]**

I also recorded on that card, in my own words, that in-database compare-and-set
was "a precondition of opening the port, not a follow-up to it". **The port is
already open on the overlay.** I do not know who opened it or when. **[U]** The
precondition I wrote down was overtaken by events, and saying so is cheaper than
discovering it during an incident.

### 1.5 One credential covers the task board *and* the VPN control plane

`scitex_cards` owns **every database on the cluster**: `scitex_cards`,
`headscale`, `scitex`, `postgres`, `sac_probe`, `scitex_cards_test_recjson`,
`scitex_state_test_credstate`, `template1`. **[M]**

Connecting with the *cards* DSN to the `headscale` database lists its tables:
`api_keys`, `pre_auth_keys`, `pre_auth_key_acl_tags`, `nodes`, `policies`,
`routes`, `users`, `migrations`. **[M]**

Since that role is a superuser and owns the database, it can read those rows.
**[I — permission follows from `rolsuper`; I listed the table names and
deliberately did not select from `api_keys` or `pre_auth_keys`.]**

So the credential every agent holds in order to file a card also reaches the
VPN's own key material. That is the concrete form of business's first
requirement for independence.

### 1.6 The filesystem defeats the role model entirely

This is the finding that governs the rest of the design.

```
uid=1000(ywatanabe) gid=1000(agent)
/home/ywatanabe/.scitex/pg/18/main   ywatanabe:agent  700
```

and from inside this agent container, as that uid, I can **list the data
directory, read `pg_hba.conf`, and list `base/`** (the heap files). `~/.pgpass`
is mode 600, owned by the same uid, 10 lines long. **[M — I checked the mode
and the line count; I did not read its contents.]**

Every agent container runs as **uid 1000, the same uid that owns the cluster's
data directory and its password file.** **[M]**

Therefore: any agent that can run a shell can read every table's bytes
directly, rewrite `pg_hba.conf`, and read the stored credentials — **without
authenticating to Postgres at all.** **[I — from the measured permissions;
I did not perform any of these three actions.]**

**A role model is only as strong as the weakest path to the same bytes.** No
GRANT, no RLS policy and no revocation in §3 changes this on its own. Any
claim that per-agent roles "separate" agents is false while this holds, and a
design that omitted it would be telling a comforting story.

**[U]** I could not measure the server process's owner: the container's PID
namespace shows only my own processes. Whether the postmaster runs as uid 1000
or as a distinct `postgres` uid is therefore unknown, and it matters — it is
the difference between "the data directory is merely readable by agents" and
"the database runs with agent privileges".

### 1.7 Tests run against the production cluster

Schemas `inbox_test` and `receipt_test` sit **inside the `scitex_cards`
database** alongside `public`, with full copies of the tables. Databases
`scitex_cards_test_recjson` and `scitex_state_test_credstate` sit beside the
production database on the same cluster. **[M]**

Not the subject of this ADR, but it bounds what "revoke superuser" can safely
do: a test suite that creates schemas needs `CREATE`, and if it gets that on
the production database the revocation is partly undone. Named here so the
migration does not discover it.

---

## 2. What this design must satisfy

From the operator's 2026-08-10 ruling (recorded on the card) and his
2026-08-23 instruction:

1. TCP on **55432**, never 5432.
2. **External connections permitted** — scitex.ai, A2A peers, agents at
   differing privilege levels. External, *not* open.
3. **Keys mandatory.**
4. **scram-sha-256**, never `trust`.
5. Per-human and per-agent **roles**, not one shared superuser.
6. **Row-level ACL enforced in the database**, not in client code.
7. **Authorship recorded as a column** — "who wrote this" must be queryable.
8. Designed for security **and** for practicality: the fleet must keep working
   throughout.

business's three requirements for "independently operable", which I adopt:

1. Credentials are stored outside the DB, where the DB's operator cannot read
   them. Today they are in the headscale config in plaintext, and the same
   person is both key-holder and DB operator, so separation cannot be claimed.
2. "Who did what" must be recoverable afterwards — and nothing not enabled
   today is recoverable for the past.
3. An auditor must be able to verify it **without our explanation**: role list,
   privileges, connection origins, audit log. If reading those requires our
   permission, it is not independent.

---

## 3. The design

### 3.1 Principals and roles

Four kinds of role, and the key move is that **`scitex_cards` stops being an
identity and becomes a privilege set**.

| role | LOGIN | purpose |
|---|---|---|
| `scitex_owner` | no | owns the schema and every table. Never used by an application. |
| `scitex_cards` | **no** (changed) | NOLOGIN group role carrying the application's DML privileges. Every agent role is a member. |
| `agent_<name>` | yes | one per agent: `agent_scitex_dev`, `agent_scitex_hub`, … Member of `scitex_cards`. |
| `human_<name>` | yes | one per human. Member of `scitex_cards`, plus whatever else that human needs. |
| `svc_<name>` | yes | CI and services (`svc_ci`). Member of `scitex_cards`, usually with a narrower grant. |
| `auditor` | yes | `pg_read_all_settings`, `pg_read_all_stats`, SELECT on the catalog and the audit log. **No DML anywhere.** |

This keeps what the operator called the common role — the shared privilege set
is real and worth having, because 30+ principals genuinely do need the same
DML rights on the same tables. What it removes is the shared *identity*.
Membership is the sharing mechanism; authentication stays per-principal.

Three properties matter and are easy to lose:

- **No application role owns a table.** RLS does not apply to a table's owner
  unless `FORCE ROW LEVEL SECURITY` is set, so ownership is a silent bypass.
  `scitex_owner` owns; applications are granted.
- **No application role has `BYPASSRLS`.** Today the only role has it. **[M]**
- **`auditor` is not a member of `scitex_cards`.** business's third
  requirement is that an auditor verify without our cooperation; an auditor who
  needs an application role to read the catalog is inside the thing they audit.

### 3.2 Authorship: derived by the database, not declared by the client

Add to every authored table:

```sql
ALTER TABLE tasks ADD COLUMN written_by name NOT NULL DEFAULT session_user;
```

and the same on `task_comments`, `notifications`, `dm_messages`,
`dm_threads`, `dm_thread_member_events`.

`session_user`, not `current_user`: `SET ROLE` changes `current_user` and
leaves `session_user` at the authenticated identity. Attribution must follow
the identity that presented a credential.

The existing `created_by` / `author` / `actor` columns **stay**, and their
meaning becomes explicit:

- `written_by` — **who connected.** Database-derived, not writable by the
  client, non-null by construction.
- `created_by` / `author` / `actor` — **who the client says wrote it.**
- `assignee` / `agent` — **who owns the work.** Legitimately different from the
  author; an agent filing a card for another agent is normal and must stay
  possible.

A row where `written_by` and the claimed author disagree is not an error — a
supervisor writing on behalf of a child is a real case — but it is now
*visible*, which it is not today. The reconciliation query is one line and
belongs in the audit surface:

```sql
SELECT written_by, created_by, count(*) FROM tasks
 WHERE created_by IS DISTINCT FROM written_by GROUP BY 1,2;
```

**Migration honesty:** the 5,888 existing rows have no `written_by`. They must
**not** be backfilled from `created_by` — that would manufacture a database-
attested fact out of a self-declared one, which is exactly the confusion this
column exists to remove. Backfill them with a literal sentinel
(`'unattested'`), so the cutover date is visible in the data rather than
smoothed over. This is business's point 2 applied to a column instead of an
extension: *what was not recorded cannot be recovered, and pretending otherwise
is worse than the gap.*

### 3.3 Row-level ACL

`ALTER TABLE … ENABLE ROW LEVEL SECURITY` plus `FORCE ROW LEVEL SECURITY` on:

| table | policy |
|---|---|
| `dm_messages`, `dm_threads`, `dm_receipts` | SELECT/INSERT only where `session_user` is a participant of the thread. |
| `notifications`, `inbox_recipients` | SELECT/UPDATE only own recipient row. |
| `tasks` | SELECT: fleet-wide (the board is shared **by design** — this is not a leak, it is the product). UPDATE: assignee, author, or a `task_roles` collaborator. DELETE: owner or a human role. |
| `task_comments` | INSERT: any member. UPDATE/DELETE: `written_by = session_user`. |

The two that change the security posture materially are the first two: **today
every agent can read every other agent's DMs and inbox**, because there is one
role. **[I — from 1.1 and the absence of any policy; I did not read another
agent's DMs to confirm it.]**

`tasks` deliberately stays fleet-readable. A design that locked the board down
would be secure and useless; the operator asked for both sides.

### 3.4 Transport and keys

- `ssl = on` with a server certificate; `hostssl` for every non-loopback line,
  so overlay and external clients cannot negotiate plaintext. Loopback keeps
  `host` — requiring TLS on `127.0.0.1` buys nothing against an attacker who
  is already uid 1000 (§1.6) and complicates local tooling.
- Replace hba line 132's `scitex_cards`-only rule with `hostssl all
  +scitex_cards 100.64.0.0/10 scram-sha-256` once per-principal roles exist —
  the group membership, not a single name, becomes the gate.
- **External (non-fleet) principals additionally require a client
  certificate**: `hostssl all +external_peers 0.0.0.0/0 cert clientcert=verify-full`.
  A2A peers at other organisations authenticate with a key they hold, not a
  password we distribute.

**One open question for the operator, and I am not going to guess it.** "Keys
are of course mandatory" has two readings: (a) TLS everywhere, passwords remain
the authenticator; (b) client certificates are the authenticator. This design
implements (a) fleet-wide and (b) for external peers, because (b) fleet-wide
means a certificate lifecycle for ~30 agents and that is a commitment, not a
config change. If he meant (b) everywhere, §4 gets a step and a schedule.

### 3.5 Audit

In increasing cost:

1. `log_connections = on`, `log_disconnections = on` — reload only.
   `log_line_prefix` already carries `%u@%d`. **[M]** This alone answers "which
   principal connected from where, when" the moment per-principal roles exist.
2. `track_commit_timestamp = on` — **requires a restart**, and records nothing
   about the past.
3. `pgaudit` — requires installing an OS package (**[M]**: not in
   `pg_available_extensions`), then `shared_preload_libraries`, then a restart.

Every one of these has an effective start date, and the design must record it
in the ADR when applied rather than leaving the log to imply coverage it does
not have. That is the same defect class as a green check that certifies less
than it appears to.

### 3.6 The custody problem, stated rather than solved

§1.6 is not fixed by anything in §3.1–§3.5. Honest options, none free:

- **(A) Move the cluster off uid 1000** — its own `postgres` uid, data
  directory outside `/home/ywatanabe`, mode 700. Agents then reach the data
  only through the port, and §3.1–§3.3 become enforceable. This is the option
  that makes the rest of this ADR true rather than decorative.
- **(B) Keep uid 1000 and state the limit** — role separation is then a
  guardrail against mistakes and confused clients, **not** a boundary against a
  hostile agent. Cheap, honest, and much weaker than it sounds when described
  as "per-agent roles".
- **(C) Move the credential store out of `~/.pgpass` and the headscale config**
  regardless of A or B, since business's first requirement is about custody,
  not about roles.

I recommend **A + C**, and I flag that A is the expensive one and that I have
not measured what depends on the current path. **[U]**

---

## 4. Migration order, and where "done" is pinned

business's sequencing, which is the same trap they found on the VPN side:

> Create the new roles and grant privileges … nobody breaks. Safe.
> Repoint each package's connection … this is the long part.
> Revoke the old role's superuser … **only here does it become safe.**
>
> **Until (c) is executed, nothing has improved from a security standpoint.**
> The trap is that you can finish (a) and (b) and report "migrated". All that
> has happened is that new roles exist; the superuser is still there. And
> during (b) *both paths are live*, so the attack surface is temporarily
> **wider**.

| step | action | breaks anything? | security gain |
|---|---|---|---|
| (a) | create `scitex_owner`, `agent_*`, `human_*`, `svc_*`, `auditor`; reassign table ownership; grant `scitex_cards` DML; write RLS policies **disabled** | no | **none** |
| (b) | repoint each package's DSN to its own role; enable RLS table by table | per-package risk | **none — surface temporarily wider** |
| (c) | `ALTER ROLE scitex_cards NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB NOLOGIN` | yes, if (b) is incomplete | **all of it** |

**The completion predicate is pinned to (c)**, and in a form that can be
measured rather than asserted:

```sql
SELECT rolsuper, rolbypassrls, rolcanlogin
  FROM pg_roles WHERE rolname = 'scitex_cards';
-- done  ==  (f, f, f)
```

**And (b) has its own predicate, which is not "the config was changed".**
business:

> (b) does not take effect until each package restarts. Long-lived processes
> keep the connection details they were started with. "I changed the setting"
> and "it is connecting with the new string" are different, and the second one
> has to be measured.

So (b) is complete when, and only when:

```sql
SELECT count(*) FROM pg_stat_activity WHERE usename = 'scitex_cards';
-- done  ==  0, sustained across a full restart cycle of every package
```

Measured right now that count is **5 client backends.** **[M]**

**One ordering constraint from outside this ADR.** Concurrency control today is
an `fcntl` lock on a local file; a remote TCP writer holds no descriptor on
this host and is not serialised by it at all. In-database compare-and-set is a
precondition for treating overlay writers as safe — and §1.4 measured that
overlay writers are **already** admitted. That makes the compare-and-set work
(`dev-lost-update-whole-card-writeback-destroys-concurrent-edits-20260810`)
*overdue*, not upcoming.

---

## 5. Who may apply this

**Not decided here, and deliberately so.**

business wrote plainly that they had touched compute-04's headscale that day —
real, reversible, verified afterwards — "but was it mine to touch? No", and
that they do not know, measured, who operates the 55432 cluster. **[U]** I do
not either. Writing a design and holding the authority to apply it are
different things, and this ADR is only the first.

What follows from that:

- This ADR is **Proposed**. Merging it changes no cluster.
- Step (a) is reversible and breaks nothing **[I — from its content; not yet
  rehearsed]**, and is still not mine to run unilaterally.
- Step (c) is the one that can lock the fleet out of its own task board. It
  needs a named owner and a rehearsed rollback before it is scheduled.
- The `dry_run`-then-enumerate-blast-radius rule applies to every step, and the
  blast radius of (c) is enumerable **only after** (b)'s predicate reads zero.

---

## 6. What this ADR does not settle

- **The tenancy unit.** business argues the VPN unit (headscale user or tag)
  and the DB unit (role) must agree or "who is this connection" has two
  answers, and that the DB should be decided first because the VPN is still
  small (4 nodes + 1 laptop) while the DB role is stepped on by every package.
  They marked that as inference, not measurement, and I record it the same way.
  **[I, business]** If scitex-net has not fixed the VPN unit, that blocks both.
- **Whether the postmaster runs as uid 1000.** §1.6. **[U]**
- **Who opened the overlay hba line, and when.** §1.4. **[U]**
- **What depends on the data directory's current path**, which option (A)
  would move. **[U]**
- **Which reading of "keys are mandatory" the operator meant.** §3.4.
