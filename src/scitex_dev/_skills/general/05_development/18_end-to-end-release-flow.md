---
description: |
  [TOPIC] End-to-end release flow (develop → PyPI) — opt-in only, per release
  [DETAILS] The authorization doctrine (default NEVER auto-release; per-release
  explicit trigger; the publication boundary comes from the leaf workflow, not a
  generic tag-push assumption), the pre-flight checklist, the full release sequence `/loop until
  pypi` exercises, the guards built into the flow (pre-push hook, branch
  protection, PEP 610 drift warning), and one-time PyPI Trusted Publisher setup
  per package. Companion to 03_release-automation.md.
tags: [scitex-general-development-release-automation]
---

# End-to-end release flow (develop → PyPI) — **opt-in only, per release**

> 🛑 **Default: NEVER auto-release.** Pushing to develop, opening a PR,
> or merging to main does NOT authorize an agent to tag and publish to
> PyPI. PyPI uploads are one-way (yanks are visible-but-not-removable),
> so each release needs its own fresh authorization — a previous
> "ship it" does not carry over to the next version.
>
> **Authorization is per-release and must be explicit.** Acceptable
> triggers:
>
> - User says "release X.Y.Z to PyPI" or "publish 0.10.18 now".
> - User says `/loop until pypi` *in the same conversation as the work
>   being released*. A `/loop` from a previous session does not roll
>   forward.
> - User confirms a `gh pr create` step explicitly mentions PyPI as
>   the intended endpoint.
>
> **Not authorization:**
>
> - "ship it", "land it", "merge it" — these are merge requests, not
>   release requests; stop after the PR merges.
> - CI being green — green CI is a precondition, not a trigger.
> - A standing `/loop` running in the background — re-confirm if the
>   release window is more than ~1 hour from the original ask.
>
> If authorization is unclear, finish a concrete, reviewable candidate
> before external publication. Existing user instructions take precedence
> over this skill; do not request permission already granted in the session.
>
> **Inspect the leaf's actual publication boundary.** A local draft tag is
> reversible. A pushed tag may trigger publication in one package and only
> validation in another. Dev currently publishes only through protected-main
> workflow dispatch; see its [release procedure](../../scitex-dev/18_full-update.md).
> Do not infer PyPI behavior from the workflow filename or from a tag existing.

**Pre-flight checklist before invoking the flow** (every box must be
true; if any is false, ship a regular dev push instead):

- [ ] User explicitly asked for a release (not "make this work" or
      "land the change" — those are merge requests, not release
      requests).
- [ ] The version bump is intentional and matches the change scope
      (patch / minor / major).
- [ ] CHANGELOG / release notes capture what shipped — drafted, not
      auto-generated boilerplate.
- [ ] Tests are green on develop, and the green run includes the
      latest commit (not a stale prior run).
- [ ] No `WIP`, `XXX`, `FIXME-blocking`, or known-broken markers in
      the diff that would trip downstream consumers.
- [ ] You can articulate, in one sentence, what would happen if this
      release contained a regression. (If the answer involves
      "everyone's CI breaks", get a second pair of eyes first.)

Once authorized, use the leaf-owned release sequence:

1. Inspect its workflow triggers, native release profile, publisher admission
   and artifact-identity requirements in the source being released.
2. Integrate accepted source through an ordinary PR. Inspect **all** checks at
   the exact head, including consent and security outcomes. Preserve failures;
   required-check branch protection alone does not establish acceptance.
3. Merge only after that review, using the reviewed head guard. Do not use
   auto-merge, administrative bypasses or synthetic verdicts.
4. Promote through the ordinary `main` release PR. Select an unused canonical
   version tag on its accepted commit; push only the intended tag.
5. Follow the actual tag-validation and publication stages. Where publication
   is a separate workflow dispatch, wait for validation and use the declared
   protected-main path. Do not substitute a manual uploader.
6. Verify published artifacts, normal dependency-compatible installation and
   installed interfaces before treating a host rollout as ready. The workflow
   may already own GitHub release creation; do not duplicate it.

Useful read-only review commands (replace placeholders):

```bash
gh workflow list --repo scitex-ai/PACKAGE
gh pr view PR_NUMBER --repo scitex-ai/PACKAGE --json headRefOid,statusCheckRollup
gh pr checks PR_NUMBER --repo scitex-ai/PACKAGE
gh run view RUN_ID --repo scitex-ai/PACKAGE
```

A pushed release tag must not be moved or force-pushed. Correct source and
qualify a new unused version when a published release needs replacement.
Preserve unsuccessful qualification records; this flow does not authorize
forced CI reruns or relaxed gates.

## PyPI Trusted Publisher Setup (one-time per package)

PyPI supports a pending Trusted Publisher that creates a new project on its
first successful publication; a manual first `twine upload` is not required.
A pending publisher does not reserve the project name. See the
[official PyPI setup guide](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

For an existing project, inspect its publishing configuration at
`https://pypi.org/manage/project/PACKAGE/settings/publishing/`.
Match the actual repository owner/name, workflow filename and environment
from the leaf's checked-in workflow. Do not copy a historical owner or
`publish-pypi.yml` filename into a different package's configuration.

Verify that the expected publisher exists before the publication boundary.
Do not replace it, introduce a different upload route or force a failed run
through. Keep registration, source qualification and artifact publication as
separate evidence.
