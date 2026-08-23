# ADR-0013 — Postgres 55432 identity: user domains, per-agent roles, DB-enforced authorship

**Status:** Proposed — design only. **This ADR grants no one permission to apply it.**
**Owner (design):** scitex-dev
**Owner (application):** UNDECIDED — see §5
**Requested by:** operator, 2026-08-23 — design the permission model, "not just
permissions — `scitex_cards` is apparently a shared role. It needs designing
from both the security side and the practical side."
**Consulted:** business (2026-08-23, four written answers)
**Evidence:** `0013-appendix-measured-baseline.md` — every measurement, with
the query that produced it
**Related:** ADR-0006 (one store per host) and its Decision 7, whose reversal
to TCP-55432 this design implements; cards
`dev-adr0006-decision7-reverse-to-tcp-55432-with-acl-20260810`,
`dev-lost-update-whole-card-writeback-destroys-concurrent-edits-20260810`,
`dev-instances-id-is-an-incarnation-not-an-instance-20260817`

---

## 0. How to read the evidence

business asked for this explicitly, and they were right to:

> Please make a column in the design document that separates "this is
> inferred, I did not measure it".

Every factual claim is tagged **[M]** measured / **[I]** inferred / **[U]**
unknown. The measurements live in the appendix; the `[U]` list is in §6 and is
not empty.

---

## 1. The baseline, in one table

Full detail and queries: `0013-appendix-measured-baseline.md`.

| what | measured, 2026-08-23 |
|---|---|
| the shared role | `scitex_cards` is `rolsuper=t rolbypassrls=t rolcreaterole=t rolcreatedb=t`, and is the **only login role** on the cluster |
| authorship | every attribution column is nullable `text` with **no default**; 5,888 tasks, 30+ `created_by` values, 147 empty; `users` registry has **0 rows** |
| audit | `pgaudit` **not in `pg_available_extensions`** — an OS package install, not a config line. `track_commit_timestamp=off`, `log_statement=none` |
| transport | `ssl = off`, while `listen_addresses` includes the overlay address and hba line 132 admits `100.64.0.0/10` |
| blast radius | `scitex_cards` owns **every** database including `headscale` — `api_keys`, `pre_auth_keys` |
| custody | agent containers run as **uid 1000**, owner of the data directory (mode 700) and `~/.pgpass`; from a container I can list `base/` and read `pg_hba.conf` |

Two of these change what can be *claimed*, not merely what should be fixed:

**`rolbypassrls = t` on the only principal** means the row-level ACL ADR-0006
Decision 7 calls for cannot be enforced against anyone who exists today. That
decision has been on the books since 2026-08-10 and is inert.

**The filesystem finding governs everything below.** A role model is only as
strong as the weakest path to the same bytes. Until the cluster moves off uid
1000, per-agent roles are a guardrail against mistakes and confused clients,
**not** a boundary against a hostile agent — see §3.6.

---

## 2. What this design must satisfy

From the operator's 2026-08-10 ruling and his 2026-08-23 instruction:

1. TCP on **55432**, never 5432.
2. **External connections permitted** — scitex.ai, A2A peers, agents at
   differing privilege levels. External, *not* open.
3. **Keys mandatory.**
4. **scram-sha-256**, never `trust`.
5. Per-human and per-agent **roles**, not one shared superuser.
6. **Row-level ACL enforced in the database**, not in client code.
7. **Authorship recorded as a column** — "who wrote this" must be queryable.
8. Security **and** practicality: the fleet must keep working throughout.

business's three requirements for "independently operable", adopted:

1. Credentials stored outside the DB, where the DB's operator cannot read
   them. Today they are in the headscale config in plaintext, and the same
   person is both key-holder and DB operator, so separation cannot be claimed.
2. "Who did what" recoverable afterwards — and nothing not enabled today is
   recoverable for the past.
3. An auditor can verify **without our explanation**: role list, privileges,
   connection origins, audit log. If reading those needs our permission, it is
   not independent.

---

## 3. The design

### 3.0 Three axes, not one — the operator's corrections

The first draft had one axis: which *agent* is connecting. The operator
rejected that within the hour, twice, and both corrections stand.

**First:**

> Isn't the common role something to do with the USER? `ywatanabe`, say —
> information tied to a user, unique. And then agents USE it. Without that,
> doesn't it fail to scale to other machines, other users, other projects?

I had designed *inside* one tenant and never asked what the tenant was.

**Second, when I named the agent as the unit of attribution:**

> An agent's identity is which host, which spec, which run — isn't it?

Also right, and it does not fit in a role. Three axes, each with a different
lifetime and a different level of attestation:

| axis | question | unit | attested by |
|---|---|---|---|
| **domain** | whose data is this? | user (`ywatanabe`) or shared group | the DB, via role membership |
| **actor** | who wrote this row? | agent, durable across runs | the DB, via `session_user` |
| **incarnation** | which host, spec, run? | one launch | **nobody — self-declared** |

Collapsing domain and actor loses something real either way. One role per
agent and no user role gives attribution and cannot express a second user, a
second machine, or a second project — the operator's first objection. One role
per user and no agent role scales, and puts `written_by = 'ywatanabe'` on all
5,888 rows, which is the self-declared authorship the appendix measured and
which he asked to fix on 2026-08-10.

Postgres expresses both, because roles are a **graph, not a tree**:
authenticate as the leaf, inherit authorization from the group.

    ywatanabe                     (NOLOGIN — the user's domain; grants live here)
      ├── ywatanabe__scitex-dev   (LOGIN — an agent acting for that user)
      ├── ywatanabe__scitex-hub   (LOGIN)
      └── ywatanabe__human        (LOGIN — the person)

`session_user` is the leaf, so attribution is per-agent. `pg_has_role()`
answers the domain question, so visibility is per-user. A second user is a
second subtree; a second machine changes nothing, because a role is not tied
to a host.

**Domains overlap, and that is a feature.** The operator asked next whether one
dataset can belong to more than one user. It can, and the change that buys it
is small and load-bearing:

> **A row's owner is a ROLE NAME, not a person's name.**

Then a shared dataset is a role (`proj_neurovista`) that several users are
members of, sharing is `GRANT proj_neurovista TO ywatanabe`, and no data
moves. The RLS predicate is the same either way:

```sql
USING (pg_has_role(session_user, owner_role, 'USAGE'))
```

The cost, stated because it is the first thing an auditor asks: **who can see
this row is no longer visible by looking at the row.** It takes a query. The
audit surface must therefore ship that query — expanding `owner_role` to its
transitive members — or the ACL is enforceable and not inspectable, which is
half a control.

**The incarnation axis cannot be a role, and pretending otherwise is the
trap.** A role is durable and needs a credential distributed to it; a run is
ephemeral and there are thousands. So the run is carried as *data*:
`application_name` set at connect time to `<host>/<spec>/<run-id>`, which
Postgres records in `pg_stat_activity` and in every log line via `%a`. That is
uniform and cheap, and it is **self-declared** — the database verifies the
role and nothing else about the string. Recording it as attested would be the
same error as trusting `created_by` today.

If run-level identity must be *attested*, the only honest mechanism is a
credential minted per launch — a short-lived certificate or password issued by
whatever starts the agent, which is the sac spawn path. That is a real option
and a real commitment; it is not in this design, and it is named here so that
"we log the run id" is never mistaken for "we can prove which run wrote this".
Same distinction the `instances.id` card makes: a launch id is not an instance
id.

**One thing this does NOT give**, and it must be said rather than discovered:
agents under the same user are **not isolated from each other**. Every agent of
`ywatanabe` inherits everything `ywatanabe` may do. That is almost certainly
correct — they act on his behalf — but it means the DM and inbox policies in
§3.3 must key on `session_user`, **not** on the domain, or they evaporate the
moment they are written.

**Naming.** Role names are unique cluster-wide, so `agent_scitex_dev` collides
the first time a second user runs an agent of the same name. Qualify them:
`<user>__<agent>`. Not cosmetic — it is the difference between the model
scaling and the model needing a rename later, under load.

**[I]** All of §3.0 is design reasoning. What is measured is that none of it
exists today: one role, no groups, no `owner_role` column, zero RLS policies.

### 3.1 Principals and roles

The key move: **`scitex_cards` stops being an identity and becomes a privilege
set.**

| role | LOGIN | purpose |
|---|---|---|
| `scitex_owner` | no | owns the schema and every table. Never used by an application. |
| `scitex_cards` | **no** (changed) | NOLOGIN group carrying the application's DML privileges — what a principal may DO. |
| `<user>` | no | NOLOGIN group naming a user's domain — WHOSE rows it may do it to (`ywatanabe`). |
| `<group>` | no | NOLOGIN group naming a shared domain (`proj_neurovista`); several users are members. |
| `<user>__<agent>` | yes | one per agent per user. Member of `scitex_cards` **and** of its user. |
| `<user>__human` | yes | the person. Same memberships, plus whatever else they need. |
| `svc_<name>` | yes | CI and services. Member of `scitex_cards`, usually a narrower grant. |
| `auditor` | yes | `pg_read_all_settings`, `pg_read_all_stats`, SELECT on the catalog and the audit log. **No DML anywhere.** |

Two group axes deliberately: `scitex_cards` answers *what may this principal
do*, the domain group answers *whose rows*. Keeping them separate is what lets
a new user reuse the whole privilege set without inheriting anyone's data.

This keeps what the operator called the common role — the shared privilege set
is real and worth having, because 30+ principals genuinely do need the same
DML rights on the same tables. What it removes is the shared *identity*.
Membership is the sharing mechanism; authentication stays per-principal.

Three properties that are easy to lose:

- **No application role owns a table.** RLS does not apply to a table's owner
  unless `FORCE ROW LEVEL SECURITY` is set, so ownership is a silent bypass.
- **No application role has `BYPASSRLS`.** Today the only role has it. **[M]**
- **`auditor` is not a member of `scitex_cards`.** business's third
  requirement is that an auditor verify without our cooperation; an auditor
  who needs an application role to read the catalog is inside the thing they
  audit.

### 3.2 Authorship: derived by the database, not declared by the client

```sql
ALTER TABLE tasks ADD COLUMN written_by name NOT NULL DEFAULT session_user;
```

and the same on `task_comments`, `notifications`, `dm_messages`,
`dm_threads`, `dm_thread_member_events`.

`session_user`, not `current_user`: `SET ROLE` changes the latter and leaves
the former at the authenticated identity. Attribution must follow the identity
that presented a credential.

The existing columns **stay**, and their meanings become explicit:

- `written_by` — **who connected.** Database-derived, not client-writable,
  non-null by construction. *Attested.*
- `written_run` — **which incarnation**, from `application_name`. Uniform and
  logged. *Declared, not attested* (§3.0).
- `created_by` / `author` / `actor` — **who the client says wrote it.**
- `assignee` / `agent` — **who owns the work.** Legitimately different from the
  author; an agent filing a card for another agent is normal and must stay
  possible.

A row where `written_by` and the claimed author disagree is not an error — a
supervisor writing on behalf of a child is real — but it becomes *visible*,
which it is not today:

```sql
SELECT written_by, created_by, count(*) FROM tasks
 WHERE created_by IS DISTINCT FROM written_by GROUP BY 1,2;
```

**Migration honesty:** the 5,888 existing rows have no `written_by`. They must
**not** be backfilled from `created_by` — that manufactures a database-attested
fact out of a self-declared one, which is exactly the confusion the column
exists to remove. Backfill a literal sentinel (`'unattested'`) so the cutover
date is visible in the data rather than smoothed over. business's point 2
applied to a column instead of an extension: what was not recorded cannot be
recovered, and pretending otherwise is worse than the gap.

### 3.3 Row-level ACL

`ENABLE` plus `FORCE ROW LEVEL SECURITY` on:

| table | policy |
|---|---|
| `dm_messages`, `dm_threads`, `dm_receipts` | SELECT/INSERT only where `session_user` is a participant. **Keyed on the agent, not the domain** (§3.0). |
| `notifications`, `inbox_recipients` | SELECT/UPDATE only own recipient row. |
| `tasks` | SELECT: `pg_has_role(session_user, owner_role, 'USAGE')`. UPDATE: assignee, author, or a `task_roles` collaborator. DELETE: owner or a human role. |
| `task_comments` | INSERT: any domain member. UPDATE/DELETE: `written_by = session_user`. |

The two that change the posture materially are the first two: **today every
agent can read every other agent's DMs and inbox**, because there is one role.
**[I — from A.1 and the absence of any policy; I did not read another agent's
DMs to confirm it.]**

Within one user's domain `tasks` stays broadly readable. A design that locked
the shared board down would be secure and useless; the operator asked for both
sides.

### 3.4 Transport and keys

- `ssl = on` with a server certificate; `hostssl` for every non-loopback line,
  so overlay and external clients cannot negotiate plaintext. Loopback keeps
  `host` — requiring TLS on `127.0.0.1` buys nothing against an attacker who
  is already uid 1000 (§3.6) and complicates local tooling.
- Replace hba line 132's single-name rule with `hostssl all +scitex_cards
  100.64.0.0/10 scram-sha-256` once per-principal roles exist — the group
  membership, not one name, becomes the gate.
- **External (non-fleet) principals additionally require a client
  certificate**: `hostssl all +external_peers 0.0.0.0/0 cert clientcert=verify-full`.
  A2A peers at other organisations authenticate with a key they hold, not a
  password we distribute.

**One open question, not guessed.** "Keys are of course mandatory" has two
readings: (a) TLS everywhere, passwords remain the authenticator; (b) client
certificates are the authenticator. This design implements (a) fleet-wide and
(b) for external peers, because (b) fleet-wide means a certificate lifecycle
for ~30 agents — a commitment, not a config change. If he meant (b)
everywhere, §4 gains a step and a schedule.

### 3.5 Audit

In increasing cost:

1. `log_connections = on`, `log_disconnections = on` — reload only.
   `log_line_prefix` already carries `%u@%d`; add `%a` so the incarnation
   string lands in every line. **[M]** This answers "which principal connected
   from where, when" the moment per-principal roles exist.
2. `track_commit_timestamp = on` — **requires a restart**, records nothing
   about the past.
3. `pgaudit` — requires installing an OS package, then
   `shared_preload_libraries`, then a restart.

Each has an effective start date, and this ADR must record it **when applied**
rather than leaving the log to imply coverage it does not have. Same defect
class as a green check that certifies less than it appears to.

### 3.6 The custody problem, stated rather than solved

The appendix's A.6 is not fixed by anything in §3.1–§3.5. Honest options, none
free:

- **(A) Move the cluster off uid 1000** — its own `postgres` uid, data
  directory outside `/home/ywatanabe`, mode 700. Agents then reach the data
  only through the port, and §3.1–§3.3 become enforceable. This is the option
  that makes the rest of this ADR true rather than decorative.
- **(B) Keep uid 1000 and state the limit** — role separation is a guardrail
  against mistakes, **not** a boundary against a hostile agent. Cheap, honest,
  and much weaker than "per-agent roles" sounds.
- **(C) Move the credential store out of `~/.pgpass` and the headscale
  config** regardless of A or B, since business's first requirement is about
  custody, not roles.

Recommendation: **A + C**. A is the expensive one, and what depends on the
current data-directory path has not been measured. **[U]**

---

## 4. Migration order, and where "done" is pinned

business's sequencing, the same trap they found on the VPN side:

> Until (c) is executed, nothing has improved from a security standpoint. The
> trap is that you can finish (a) and (b) and report "migrated". All that has
> happened is that new roles exist; the superuser is still there. And during
> (b) *both paths are live*, so the attack surface is temporarily **wider**.

| step | action | breaks anything? | security gain |
|---|---|---|---|
| (a) | create `scitex_owner`, domain groups, `<user>__<agent>`, `auditor`; reassign table ownership; grant DML; write RLS policies **disabled** | no | **none** |
| (b) | repoint each package's DSN to its own role; enable RLS table by table | per-package risk | **none — surface temporarily wider** |
| (c) | `ALTER ROLE scitex_cards NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB NOLOGIN` | yes, if (b) is incomplete | **all of it** |

**Completion is pinned to (c)**, measurable rather than asserted:

```sql
SELECT rolsuper, rolbypassrls, rolcanlogin
  FROM pg_roles WHERE rolname = 'scitex_cards';
-- done  ==  (f, f, f)
```

**And (b) has its own predicate, which is not "the config was changed."**
business:

> (b) does not take effect until each package restarts. Long-lived processes
> keep the connection details they were started with. "I changed the setting"
> and "it is connecting with the new string" are different, and the second one
> has to be measured.

```sql
SELECT count(*) FROM pg_stat_activity WHERE usename = 'scitex_cards';
-- done  ==  0, sustained across a full restart cycle of every package
```

Measured now: **5 client backends.** **[M]**

**One ordering constraint from outside this ADR.** Concurrency control today is
an `fcntl` lock on a local file; a remote TCP writer holds no descriptor on
this host and is not serialised by it at all. In-database compare-and-set is a
precondition for treating overlay writers as safe — and A.4 measured that
overlay writers are **already** admitted. That work is **overdue, not
upcoming**.

---

## 5. Who may apply this

**Not decided here, deliberately.**

business wrote that they had touched compute-04's headscale that day — real,
reversible, verified afterwards — "but was it mine to touch? No", and that
they do not know, measured, who operates the 55432 cluster. **[U]** I do not
either. Writing a design and holding the authority to apply it are different
things.

- This ADR is **Proposed**. Merging it changes no cluster.
- Step (a) is reversible and breaks nothing **[I — from its content; not
  rehearsed]**, and is still not mine to run unilaterally.
- Step (c) can lock the fleet out of its own task board. It needs a named
  owner and a rehearsed rollback before it is scheduled.
- The dry-run-then-enumerate-blast-radius rule applies to every step, and (c)'s
  blast radius is enumerable **only after** (b)'s predicate reads zero.

---

## 5b. The cross-host reconciler is a principal this design has no place for

Raised by scitex-cards, 2026-08-23, and it is a real gap rather than a detail.

A per-row reconciler exists in `scitex_cards/cardsync/` and is read-only today.
Its dry run against compute-03, that evening:

    inspected 5945   already_equal 2938
    would_write_to_a 159   would_write_to_b 2665   unresolved 183

**2,665 of those writes land on ANOTHER HOST'S STORE**, and they are writes to
cards owned by many different agents. Under §3.1 that is not expressible. It is
not an agent acting for a user; it is one process writing rows on behalf of
principals it is not. The two ways to admit it are both bad:

* give it a service role with broad DML across every domain — which makes the
  row-level ACL of §3.3 decorative, since the busiest writer bypasses it;
* give it per-card delegated authority — which needs a delegation mechanism
  that does not exist and would have to be designed before the roles are cut.

So a design that cuts per-principal roles without answering this either breaks
sync or hands sync a key to everything. **[U]** — I have not designed either
option and am not proposing one here; the point is that the migration in §4
cannot be scheduled until somebody has.

MEASURED, and it sharpens §3.0's third axis: `application_name` is **unset on
every connection** to this store —

    select application_name, count(*) from pg_stat_activity
      where backend_type = 'client backend' group by 1;
    -> [('(unset)', 5)]

§3.0 proposes carrying `<host>/<spec>/<run-id>` there as the incarnation axis.
Today that field is empty fleet-wide, so the axis has **zero adoption**, not
partial adoption. That is fine for a proposal and must not be read as
describing something that exists. It also means the reconciler is, right now,
indistinguishable at the database from any agent — the one writer whose
identity would matter most is the one with none.

ONE MORE THING WORTH KNOWING BEFORE THE ROLES ARE CUT, measured on this host:
the syncer the fleet actually runs is `~/.local/bin/scitex-cards-sync-peers.sh`
→ `scitex-cards-sync.py`, and **neither file is in any git repository**. So the
process that would need a role under this design is not covered by any audit,
test or review gate that a role assignment would be reasoned against. That is
scitex-cards' and sac's to resolve, not this ADR's, but a role model drawn
around code nobody can see is drawn around a guess.

## 6. What this ADR does not settle

- **Whether the domain unit and the VPN unit agree.** business argues the VPN
  unit (headscale user or tag) and the DB unit must match or "who is this
  connection" has two answers, and that the DB should be decided first because
  the VPN is still small (4 nodes + 1 laptop) while the DB role is stepped on
  by every package. Marked by them as inference, not measurement. **[I,
  business]** If scitex-net has not fixed the VPN unit, that blocks both.
- **Whether run-level identity must be attested**, which would mean per-launch
  credentials (§3.0). Not designed here.
- **Whether the postmaster runs as uid 1000.** **[U]**
- **Who opened the overlay hba line, and when.** **[U]**
- **What depends on the data directory's current path**, which option (A)
  would move. **[U]**
- **Which reading of "keys are mandatory" the operator meant.** §3.4.
