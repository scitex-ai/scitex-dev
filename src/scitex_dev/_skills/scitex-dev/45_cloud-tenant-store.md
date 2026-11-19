---
description: |
  [TOPIC] Private PostgreSQL tenant stores.
  [DETAILS] Provisioning boundaries and adversarial validation for hosted consumers.
tags: [scitex-dev-cloud-tenant-store]
---

# Cloud tenant stores

This opt-in primitive does not certify the managed 55432 deployment.
Resolve the authenticated application's stable user UUID
on the server. Request headers, display names, `actor`, and user-settable
database settings cannot establish database identity.

`TenantScope(UUID)` derives an unprivileged login and private namespace.
`provision_tenant_store()` creates new Store tables only. A separate NOLOGIN
owner owns the namespace and tables; tenant logins receive USAGE, SELECT,
INSERT, and necessary UPDATE privileges, with no role memberships, namespace
CREATE, DELETE, or TRUNCATE. Existing tables require an explicit migration.

All four physical tables have ENABLE and FORCE RLS, including oplog payloads,
cursors, and identity metadata. A restrictive PUBLIC boundary checks
`session_user` against the tenant login, alongside the tenant's permissive
policy. `open_tenant_store()` checks identity, namespace, role attributes,
table ownership, policies, and destructive privileges before opening rows.
An unavailable or weakened store raises; no shared-store fallback exists.

Use a PgBouncer pool that preserves the tenant's backend login. A forced
shared database user fails the identity check. Verify backend identity and
namespace through the actual pool, including reuse; a direct PostgreSQL
experiment does not prove its configuration. Session pooling is the initial
deployment target. Transaction pooling and PostgreSQL 18 require separate
experiments. Statement pooling cannot support multi-statement Store
transactions. See [PgBouncer configuration](https://www.pgbouncer.org/config.html).

RLS does not protect TRUNCATE, and superusers/BYPASSRLS can bypass policies.
Keep migrations and privileged roles outside request workers. See
[PostgreSQL row security](https://www.postgresql.org/docs/18/ddl-rowsecurity.html).
The connection-catalogue check is not a defense against a privileged operator
changing policies while a connection is already open.

Run the adversarial tests on an explicitly disposable local cluster, with
synthetic UUID users and rows. Cover all metadata tables, broad accidental
grants, permissive policy additions, raw SQL, forged context, impersonation,
destructive operations, weakened policies, and concurrent requests.
Report engine/pool versions and skipped gates. These experiments do not
authorize production provisioning or adoption of owner-ambiguous shared rows.

Cross-owner project sharing and host replication are not implemented by this
primitive. They need explicit project capabilities and replication semantics
that preserve tenant identity and never grant a full owner login to a reader.
