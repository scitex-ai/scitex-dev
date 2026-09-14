---
description: |
  [TOPIC] Access primitive — scitex_dev.access check() / accessible()
  [DETAILS] The one "may this principal do this to that resource, and which rows may it list" primitive every SciTeX app asks: principals (user/org/agent/anonymous), roles read<write<admin, owner/grant/inherited/org/public rules, the agent ceiling, no staff bypass, the scitex-access/1 decision record with exit codes 0/10/11, kind registration via the scitex_dev.access.kinds entry point, the `<pkg> dev access` CLI, and the equivalence suite adapters must pass.
tags: [scitex-dev-access-primitive]
---

# Access primitive (`scitex_dev.access`)

ADR: [docs/adr/0014-access-primitive-v1.md](../../../../docs/adr/0014-access-primitive-v1.md).
Every app is visible to everyone; its CONTENT is filtered by this primitive,
never by per-app gates.

## Asking one question

```python
from scitex_dev.access import Grant, Membership, Principal, Resource, check

doc = Resource(kind="writer.manuscript", path="/users/alice/writer/m1",
               owner=Principal.parse("user:alice"),
               parent="writer.project:/users/alice/writer")
decision = check(Principal.parse("agent:alice/bot"), "edit", doc,
                 grants=[Grant(Principal.parse("agent:alice/bot"), "write", doc.ref)],
                 memberships=[])
decision.kind, decision.reason   # DecisionKind.ALLOWED, Reason.GRANT
decision.http_status, decision.exit_code
decision.to_dict()               # scitex-access/1 record
```

`require(...)` is the same call, raising `AccessDenied` (a `PermissionError`)
or `AccessUnresolved` (a `RuntimeError`) unless allowed.

## Rules

| reason | when |
|---|---|
| `owner` | the resource's owner (a user or org) holds admin |
| `grant` | an explicit grant on the resource |
| `inherited` | a `default=True` grant on the resource's parent |
| `org` | via an org membership, capped at the membership role |
| `public` | public visibility gives read to everyone, including anonymous |
| `not-visible` | no role on a private resource; renders as 404, like a missing one |
| `role-too-low` | a weaker role than the action needs |
| `agent-ceiling` / `owner-has-no-role` | `agent:<owner>/<name>` is capped by its owner's role |
| `not-signed-in` | anonymous, and signing in might help |
| `kind-unregistered` | no package registers the kind: unresolved, fails closed |

There is no staff bypass. An instance administrator is an org membership plus
a grant, like anyone else.

## Listing rows

```python
from scitex_dev.access import accessible
f = accessible(Principal.parse("user:bob"), "view", "writer.manuscript",
               grants=grants, memberships=memberships)
f.to_dict()   # owners, resources, parents, public, ceiling (agents)
```

An adapter translates the filter once, into a Django `Q` or a store query, then
proves the translation agrees with `check()`:

```python
from scitex_dev.access.testing import assert_equivalent
assert_equivalent(my_selector)  # selector(filter, fixture) -> refs
```

## Registering a kind

```toml
[project.entry-points."scitex_dev.access.kinds"]
scitex-writer = "scitex_writer._access_kinds:provide"
```

```python
def provide():
    return [KindSpec(name="writer.manuscript", path_prefix="/",
                     actions={"view": "read", "edit": "write", "share": "admin"})]
```

## CLI

```bash
<pkg> dev access list-kinds [--all] [--json]
<pkg> dev access check --principal user:alice --action edit \
    --resource writer.manuscript:/users/alice/writer/m1 --fixture world.json [--json]
```

Exit 0 means allowed; 10 means denied, not signed in or not entitled; 11 means
unresolved. v1 has no persistence, so grants come from `--fixture` (see
`AccessFixture`). A leaf mounts the group with
`register_access_group(dev, pkg="<dist>")`.
