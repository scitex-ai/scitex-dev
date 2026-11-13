---
description: |
  [TOPIC] Reviewed develop-to-main promotion
  [DETAILS] Follow the owning package's protected source, tag and publication boundaries. Dev requires release source already promoted to protected main; a tag push validates the source and builds, while publication is a separate main dispatch. Companion to version control and the end-to-end release flow.
tags: [scitex-general-development-version-control]
---

# Reviewed develop-to-main promotion

Follow the package's checked-in release workflow and current user authorization.
Main promotion, tag validation, publication and host rollout are separate stages.
The sequence is in [the release flow](18_end-to-end-release-flow.md); branch
review conventions are in [version control](01_version-control.md).

## Current Dev boundary

Dev's release caller is
[the tag/publication workflow](https://github.com/scitex-ai/scitex-dev/blob/4e14fe28571617ccf7b6fffd9cff0e15a7bfc38c/.github/workflows/pypi-publish-and-github-release-on-tag.yml).
A tag push runs source validation and the whole test/build profile. Publication
requires a separate workflow dispatch from protected `main`, using the existing
`pypi` environment and Trusted Publisher identity. Dev has no checked-in
`.github/workflows/sync-main.yml` at this reviewed source.

The shared
[source qualifier](https://github.com/scitex-ai/.github/blob/4b2175758b236d57a90918a196f723b7400f0bbd/.github/workflows/ci-sif-matrix.yml)
checks the tag's resolved commit against protected `main` before and after the
comparison. It refuses unpromoted source, a changing main head, mismatched tag
events and a publication dispatch outside `main`. Its `DEV_RELEASE_SOURCE`
controls are exercised in the shared repository's
[release contract tests](https://github.com/scitex-ai/.github/blob/4b2175758b236d57a90918a196f723b7400f0bbd/tests/test_dev_release_contract.py).
These links identify reviewed evidence; inspect current owning source before
using the procedure for a later release.

Promote the reviewed source through an ordinary `develop` to `main` PR, accept
its exact-head checks and original post-merge checks, then select an unused
canonical tag on the accepted source. Follow the owning tag-validation and
publication stages. A tag is not a mechanism for advancing Dev's main branch.

Other packages can have different workflows. Inspect their actual triggers and
source-admission checks rather than copying Dev's sequence or an automatic-sync
template. Keep in-flight work on `develop`; preserve existing failures and
immutable tags. Version reconciliation and an installed version match do not
establish release acceptance.
