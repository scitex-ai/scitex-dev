---
description: |
  [TOPIC] Deployment and installed-interface verification
  [DETAILS] Select compatible published artifacts, preserve host data, use leaf-owned deployment procedures and verify installed and running interfaces separately. No generic compose-stop or forced-retag recipe.
tags: [scitex-dev-release-deploy]
---

# Deployment and installed-interface verification

Continue only with accepted artifacts from
[18_full-update.md](18_full-update.md). An accepted source commit, published
artifact, installed environment and running service are separate observations.

## Select the target environment

Resolve hosts through the [host registry](24_host-registry.md). Inspect the
actual service interpreter, package versions, dependency constraints and leaf
configuration before installing anything. Preserve dirty authority checkouts,
user data and unrelated packages; prepare an owned worktree or candidate
profile for qualification.

Use a normal installation of the declared extras and run `python -m pip check`
with that profile's interpreter. Do not override dependency pins to make a
candidate install. A source-only test or `PYTHONPATH` override does not prove
that a published wheel supplies the same code and resources.

## Follow the leaf's deployment procedure

Hub owns its builds, migrations, rollout, data preservation and rollback.
Discover its installed instructions through the umbrella CLI:

```bash
scitex dev skills list --package scitex-hub --json
```

This command's package/JSON options are available in the qualified installed
CLI. Skill routing and deprecation notices can differ across installed Root
and Dev versions; inspect actual help for the selected environment.

Read the discovered Hub release/deployment skill before changing a service.
The legacy `deploy_scitex_hub` helper targets an older layout and is not the
current production procedure. Do not substitute a blanket compose stop/build
or an unqualified remote editable install. Keep the current service available
until the leaf's checked rollout and rollback conditions are satisfied.

## Verify adoption

Record the exact artifact and installed profile, then check representative
Python imports, CLI commands, MCP registration, admitted Web operations and
skill discovery. A surface may be intentionally unavailable; report its reason
rather than treating metadata presence as a reachable interface.

For Hub, verify public and authenticated routes, runtime versions and relevant
browser behavior, including light/dark and mobile views. Keep simulator,
physical-device and desktop coverage distinct. A successful health request
alone is not visual or functional acceptance.

Skill installation and projection are explicit target changes. Inspect
`scitex dev skills install --help` in the installed environment before choosing
a destination; do not assume an unreleased flag or silently project skills
into every vendor directory. See [12_config.md](12_config.md).

If adoption fails, preserve evidence and use the leaf's rollback procedure.
Do not move a published tag, force a checkout, stash unrelated edits, discard
user data or label an older running service as updated.
