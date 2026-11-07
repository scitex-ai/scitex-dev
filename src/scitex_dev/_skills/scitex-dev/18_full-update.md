---
description: |
  [TOPIC] Release preparation and publication
  [DETAILS] Source-owned Dev release contract: exact-head checks, setuptools-scm versions, immutable tag validation, and protected-main manual OIDC publication. Leaves own their release procedures.
tags: [scitex-dev-full-update]
---

# Release preparation and publication

Use the package being released as the source of truth. Dev dispatches checks;
its release workflow does not define publication for every leaf. Host rollout
is a separate step: [19_release-deploy.md](19_release-deploy.md).

## Current Dev workflow

Inspect `.github/workflows/pypi-publish-and-github-release-on-tag.yml` in the
source under review. Despite its historical filename, its current behavior is:

| Event | Behavior |
|---|---|
| Push a `v*` tag | Validate immutable source through the `dev-release` native test/build profile; no PyPI upload or GitHub release |
| Dispatch the workflow on `main`, with an existing `version` tag | Repeat test/build qualification, then publish through the admitted `pypi` environment; create the GitHub release only after publication succeeds |

Organization admission, source/runtime/image closure, wheel/sdist identity and
RECORD checks remain mandatory. A green ordinary PR is not a release-profile
or installed-artifact qualification.

## Prepare the candidate

1. Confirm the user's release scope and inspect clean/dirty source, current
   tags and published versions. Preserve unrelated work; use an owned worktree.
2. Review changes since the last release and write accurate changelog entries.
   Dev derives its version from release tags using `setuptools-scm`; do not
   assume a static version field in `pyproject.toml` or overwrite `__init__.py`.
3. Check README, docs and skills against source and actual command help. Keep
   static, behavioral, artifact and served-document evidence separate. Use the
   [documentation-drift skill](../general/05_development/22_documentation-drift.md).
4. Integrate accepted source and qualify the combined tree. Review every PR
   check at the exact head, including optional consent/security failures.
   Merge normally with the reviewed head guard; do not enable auto-merge or
   bypass a failed check.
5. Promote through the ordinary release PR to `main`. After all checks pass,
   choose an unused canonical version tag on the accepted main commit. Push
   only that tag, never a blanket `--tags` push. Published tags are immutable.

## Publish only the qualified tag

After the tag-triggered validation completes, inspect its entire outcome.
Publication, when authorized, uses this workflow's `workflow_dispatch` from
`main` with `version` set to that existing tag. Do not replace that path with
manual uploads, a different publisher, synthetic verdicts or relaxed checks.

The workflow owns GitHub release creation after PyPI succeeds. Verify the
published wheel/sdist identities, normal installation with the declared
extras, dependency consistency and documented interfaces separately. Do not
infer success from a tag or GitHub release page alone.

Preserve failed-run evidence. Diagnose source or infrastructure failures before
attempting the next normal qualification; this playbook does not request
forced reruns, tag replacement or automatic host updates.
