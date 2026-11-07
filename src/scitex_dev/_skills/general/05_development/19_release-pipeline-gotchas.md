---
description: |
  [TOPIC] Release qualification failure modes
  [DETAILS] Exact-head CI coverage, declared consent policy, immutable tags, archive identity and bounded recovery. Source, published artifacts and running services require separate evidence.
tags: [scitex-general-development-release-automation]
---

# Release qualification failure modes

Use the leaf's checked-in workflow and
[18_end-to-end-release-flow.md](18_end-to-end-release-flow.md). Publication
triggers, native profiles and publisher identities differ between packages.

## Local checks and CI cover different environments

An editable auditor can differ from the version installed in CI. Record the
actual interpreter, distribution versions, source tree and declared extras.
A local audit is evidence for that context, not a substitute for the full
native suite at the final PR head.

Inspect all checks and their underlying job outcomes. Required-check branch
protection alone does not clear optional consent/security failures, and a
successful relay does not establish that the intended tests ran. Retain failed
runs, skipped scopes and unresolved infrastructure failures explicitly.

## Protected branches and consent are release boundaries

Use the ordinary PR path and reviewed head guard. Do not escalate to an
administrative merge, change protections or manufacture a successful status.
If a check contradicts the intended contract, fix its source and qualify the
change through normal review; do not suppress it just to release.

Read the caller's existing CLA policy and the complete commit range. Match
contributors to that declared policy and real consent records. Do not add an
allowlist entry, impersonate a signer or change the ledger to clear a release.
A transport/baseline attribution rule requires its own existing proof; it is
not permission to ignore an uncovered contributor.

## Published tags and artifact filenames are immutable

Never delete, move or force-push a published release tag. When source or
artifact bytes must change, qualify a new unused version. An unsuccessful
upload does not by itself prove that PyPI reserved the whole version; inspect
what actually reached the index and preserve the original failed run.

Use the leaf's declared validation/publication stages to resolve a publication
failure. Do not assume that forcing a CI rerun, changing upload routes or
replacing a tag is the next step.

## Inspect duplicate archive members before changing packaging

A redundant Hatch `force-include` entry can include a resource already selected
by its package configuration. Inspect the actual wheel/sdist entries and
RECORD identities before removing the redundant declaration. Preserve intended
resources and rerun the normal artifact checks after a packaging fix; a
successful build alone does not prove a correct archive.

## Keep provider recovery separate from release qualification

A model account cap, provider outage and CI/storage failure have different
causes. Do not rotate accounts, restart agents or launch billable probes as a
release workaround. Use the responsible leaf's recovery skill and its evidence,
admission and restart limits when that recovery is authorized. Keep credentials
and operator account details out of general skills and release reports.
