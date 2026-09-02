# ADR-0013 appendix — what was measured on the 55432 cluster

Companion to `0013-postgres-55432-identity-per-principal-roles-and-db-enforced-authorship.md`.
This file holds the evidence; the ADR holds the decision. Split so the ADR
stays readable and so a later re-measurement can replace this file wholesale
without touching the design.

All of it is **read-only**, taken 2026-08-23. Nothing was changed on the
cluster to produce it. Tags: **[M]** measured, **[I]** inferred, **[U]**
unknown.

Cluster: PostgreSQL **18.4 (Debian 18.4-1.pgdg13+1)** on port **55432**,
`data_directory = /home/ywatanabe/.scitex/pg/18/main`, reached with the DSN
`scitex_cards.resolve_store()` returns:
`postgresql://scitex_cards@127.0.0.1:55432/scitex_cards`. **[M]**

## A.1 The shared role is a superuser, and it is the only login role

```
rolname       | rolsuper | rolcreaterole | rolcreatedb | rolcanlogin | rolbypassrls
scitex_cards  | t        | t             | t           | t           | t
```

`pg_roles` holds **17 rows: 16 built-in `pg_*` roles and `scitex_cards`.** No
other role can log in. **[M]**

So "a shared role" is correct and understates it. It is a shared
**superuser**, held by every agent, every package and CI. `rolbypassrls = t`
additionally means this role ignores row-level security, so the row-level ACL
that ADR-0006 Decision 7 calls for **cannot be enforced against the only
principal that exists.** **[M]**

## A.2 Authorship is a self-declared string with no default and no constraint

Every attribution column is `text`, nullable, with **no column default**:
`tasks.created_by`, `tasks.agent`, `tasks.assignee`, `task_comments.author`,
`notifications.actor`, `notifications_quarantine.actor`,
`dm_threads.created_by`, `dm_thread_member_events.actor`. **[M]**

The board holds **5,888 tasks across 30+ distinct `created_by` values** —
`scitex-agent-container` 1,477, `scitex-cards` 688, `scitex-hub` 642,
`scitex-dev` 501, `ci` 438, `operator` 58, … **and 147 rows where `created_by`
is empty.** **[M]**

Because all 30+ of those principals authenticate as the same role, the
database cannot distinguish them. **Any client holding the DSN can write any
author string, including `operator`.** **[I — follows from A.1 plus the absence
of any default or trigger; I did not attempt a forged write, and will not.]**

The `users` table — the registry that would say which principals exist —
contains **0 rows.** **[M]**

## A.3 Nothing is auditable, and the audit extension is not merely uninstalled

```
track_commit_timestamp   | off   (default)
log_connections          | ''    (default)
log_disconnections       | off   (default)
log_statement            | none  (default)
shared_preload_libraries | ''    (default)
pg_extension             | plpgsql only
```

**[M]**

`pg_available_extensions` offers `pgcrypto` and `sslinfo`. **`pgaudit` is not
in the list at all** — it is not installed on the host, so enabling it is an
OS package installation, not a configuration line. **[M]** business reported
pgaudit as "not enabled"; that it is not *available* is the stronger fact, and
it changes who has to act and how long it takes.

Their consequence is why it matters:

> What is not enabled cannot be recovered retroactively. Enable it today and
> everything before today is still empty. If audit is the goal, "when did you
> turn it on" becomes the effective start date of the audit.

## A.4 TLS is off, and the overlay is already reachable

```
ssl              | off                    (default)
listen_addresses | 127.0.0.1,100.64.0.1   (configuration file)
port             | 55432                  (configuration file)
log_line_prefix  | %m [%p] %q%u@%d        (configuration file)
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

Line 132 is `100.64.0.0/10` — the whole CGNAT range the overlay uses. **Every
node on the overlay can already attempt to authenticate as the shared
superuser**, and the only thing between an overlay node and the cluster is
that role's password. Transport confidentiality comes from the overlay's own
encryption, **not** from Postgres: `ssl = off`. **[M]**

The operator's condition on the 2026-08-10 reversal was that keys are of
course mandatory. **That condition is not in effect today.** **[M]**

I also recorded on that card, in my own words, that in-database compare-and-set
was "a precondition of opening the port, not a follow-up to it". **The port is
already open on the overlay.** I do not know who opened it or when. **[U]** The
precondition was overtaken by events, and saying so is cheaper than
discovering it during an incident.

## A.5 One credential covers the task board *and* the VPN control plane

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
VPN's own key material.

## A.6 The filesystem defeats the role model entirely

This is the finding that governs the design.

```
uid=1000(ywatanabe) gid=1000(agent)
/home/ywatanabe/.scitex/pg/18/main   ywatanabe:agent  700
```

From inside this agent container, as that uid, I can **list the data
directory, read `pg_hba.conf`, and list `base/`** (the heap files).
`~/.pgpass` is mode 600, owned by the same uid, 10 lines long. **[M — mode and
line count only; I did not read its contents.]**

Every agent container runs as **uid 1000, the same uid that owns the cluster's
data directory and its password file.** **[M]**

Therefore any agent that can run a shell can read every table's bytes
directly, rewrite `pg_hba.conf`, and read the stored credentials — **without
authenticating to Postgres at all.** **[I — from the measured permissions; I
performed none of these three actions.]**

**A role model is only as strong as the weakest path to the same bytes.** No
GRANT, no RLS policy and no revocation changes this on its own. Any claim that
per-agent roles "separate" agents is false while this holds.

**[U]** The server process's owner could not be measured: the container's PID
namespace shows only my own processes. Whether the postmaster runs as uid 1000
or as a distinct `postgres` uid is unknown, and it matters — it is the
difference between "the data directory is merely readable by agents" and "the
database runs with agent privileges".

## A.7 Tests run against the production cluster

Schemas `inbox_test` and `receipt_test` sit **inside the `scitex_cards`
database** alongside `public`, with full copies of the tables. Databases
`scitex_cards_test_recjson` and `scitex_state_test_credstate` sit beside the
production database on the same cluster. **[M]**

Not the ADR's subject, but it bounds what "revoke superuser" can safely do: a
test suite that creates schemas needs `CREATE`, and if it gets that on the
production database the revocation is partly undone. Recorded so the migration
does not discover it.
