---
description: |
  [TOPIC] Gotchas across the release pipeline
  [DETAILS] Recurring failure modes when releasing scitex-* packages, none
  obvious from a green local audit: gh-CI is the only trustworthy merge gate
  (local `audit-all` can lie when the editable install is behind the CI-pinned
  auditor); `enforce_admins=true` cannot be bypassed by `gh pr merge --admin`;
  the no-retag rule (burned/stale tag → PATCH bump); PyPI 400 duplicate-filename
  (hatchling `force-include`); CLA allowlist must end with `,ywatanabe1989`; and
  releasing under quota pressure (429 vs 529). Companion to 03_release-automation.md.
tags: [scitex-general-development-release-automation]
---

# Gotchas across the release pipeline

These are recurring failure modes when releasing scitex-* packages. None of
them are obvious from a green local audit — keep this section handy.

### gh-CI is the ONLY trustworthy merge gate (local `audit-all` can lie)

An **editable** local `scitex-dev` install can be older than the PyPI build
pinned by a target repo's CI (e.g. CI pins `scitex-dev[cli-audit]==<latest>`
while local is two patches behind → missing audit rules like PA-306 no-mocks
or PA-307 TQ). Local `audit-all` then reports green while CI fails the same
checks.

Always verify the **gh-CI** state before merging:

```bash
gh pr checks <PR#>           # required checks on the PR
gh run list --branch develop --limit 3
```

Subagents that report "local green" should re-verify in a throwaway venv
with the CI-pinned auditor before claiming a clean state.

### `enforce_admins=true` cannot be bypassed by `gh pr merge --admin`

When a repo's `develop` (or `main`) has branch protection with
`enforce_admins: true` (socialia, str, scholar, …), even `gh pr merge --admin`
won't override a FAILING required check. The work must be genuinely complete
(CI green), not "merged anyway". If a check is wrong, fix the check or the
ruleset — don't escalate to admin-merge as a habit.

### No-retag rule — burned/stale tag → PATCH bump

If a tag push fired the publish workflow but the upload failed (e.g. the
trusted-publisher save silently dropped above, or `pytest tests/ -x` red),
**never delete and recreate the tag.** PyPI remembers the (project, version)
pair as taken even on failed uploads; a deleted-then-recreated tag is
effectively a burned slot. Re-release via a PATCH bump (`0.2.20` burned
→ `0.2.21`). Same rule for filename-level collisions (different sdist/wheel
hash for the same version).

### PyPI 400 `Duplicate filename in local headers` (hatchling)

If publishing throws

```
HTTPError: 400 Bad Request from https://upload.pypi.org/legacy/
Duplicate filename in local headers
```

this is **hatchling-specific**: `force-include` of `_sphinx_html` (or any
path already covered by the auto-discovered `packages=` setting) emits the
file twice in the wheel header table. Drop the redundant
`tool.hatch.build.targets.wheel.force-include` entry. setuptools-built
packages are not affected.

### CLA Assistant allowlist must end with `,ywatanabe1989`

Bare `bot*` blocks **maintainer-authored release PRs** because the release
flow opens the develop→main PR as a human commit, not a bot. The allowlist
must read:

```yaml
allowlist: bot*,ywatanabe1989
```

`pull_request_target` reads `cla.yml` from the **base branch (main)**, so if
the allowlist is correct on develop but stale on main the gate still fails
on the release PR. Fix on main, not develop.

### Releasing under quota pressure (parallel-publish bottleneck)

When ~N packages need releasing in the same window and the lead's Anthropic
Max account is rate-limited, **don't serialise the campaign as a "fix"** —
that just stretches the wall-clock without addressing the cause. Spread the
release work across the 3 Max accounts (lead session
`ywatanabe@scitex.ai`; campaign agents `wyusuuke@gmail.com` /
`ywata1989@gmail.com`) and stagger dispatches ~45 s apart to avoid a
first-turn spike. Distinguish:

- **429 / "out of extra usage"** → per-account; rotate the responsible
  agent to a different account.
- **529 overload** → Anthropic server-side, transient; switching accounts
  does NOT help. Wait.

These are operational notes; the structural release flow above is
unaffected.
