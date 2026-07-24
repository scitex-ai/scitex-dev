---
description: |
  [TOPIC] End-to-end release flow (develop → PyPI) — opt-in only, per release
  [DETAILS] The authorization doctrine (default NEVER auto-release; per-release
  explicit trigger; the trust boundary is `git push origin <v-tag>`, not the
  local tag), the pre-flight checklist, the full release sequence `/loop until
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
> If in doubt: stop after the GitHub release step and ask before
> pushing the `v*` tag (that tag is the trigger that PyPI cannot
> undo).
>
> **Trust boundary: `git push origin <v-tag>`, not the tag itself.**
> Local `git tag -a vX.Y.Z -m ...` is a free, reversible scratch
> action — `git tag -d` cleans it up. Nothing on PyPI fires until
> the tag is *pushed*: `publish-pypi.yml` triggers on the GitHub
> `push` event filtered by `tags: [v*]`. So drafting a tag locally
> for review is fine; the moment of authorization is the push.

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

The full release sequence below is what `/loop until pypi` exercises
once those preconditions hold:

```bash
# 0. Confirm CI is green on develop.
gh run list --repo ywatanabe1989/<pkg> --branch develop --limit 3

# 1. Open release PR develop → main.
#    The pre-push hook in .git/hooks/pre-push BLOCKS direct pushes to
#    main, so always go via PR (do NOT use --no-verify).
gh pr create --repo ywatanabe1989/<pkg> --base main --head develop \
  --title "Release X.Y.Z — <one-line summary>" \
  --body "<changelog body — bullet points + Test plan>"

# 2. Auto-merge once required checks pass.
gh pr merge <PR#> --repo ywatanabe1989/<pkg> --merge --auto

# 3. After merge lands, tag origin/main and push the tag.
#    The publish-pypi.yml workflow triggers on `v*` tags.
git -C <repo> fetch origin main
git -C <repo> tag -a vX.Y.Z origin/main -m "vX.Y.Z — <summary>"
git -C <repo> push origin vX.Y.Z

# 4. Create the GitHub release (release notes for humans).
gh release create vX.Y.Z --repo ywatanabe1989/<pkg> \
  --title "vX.Y.Z — <summary>" \
  --notes "<release notes>"

# 5. Watch the publish workflow run.
gh run list --repo ywatanabe1989/<pkg> --workflow publish-pypi.yml --limit 1
```

Guards built into the flow:

- **Pre-push hook** (`.git/hooks/pre-push`) refuses direct pushes to
  `main`/`master`. Forces the PR path. Never bypass with `--no-verify`.
- **Branch-protection** on `main` requires CI green before merge — the
  PR-merge step waits for checks even with `--auto`.
- **PEP 610 `direct_url.json`** is read by the editable-install drift
  warning; if you forget to bump and re-tag, downstream editable
  consumers see a one-line stderr nudge on next `import <pkg>`.

## PyPI Trusted Publisher Setup (one-time per package)

First PyPI release must be a manual `twine upload` (trusted publishing cannot create a *new* project — it can only publish to an *existing* one). After that, configure the trusted publisher so tag-triggered GitHub Actions can publish without tokens.

Per-package settings URL:

```
https://pypi.org/manage/project/<pkg-name>/settings/publishing/
```

Fill in:

| Field | Value |
|---|---|
| PyPI project name | `<pkg-name>` (auto) |
| Owner | `ywatanabe1989` |
| Repository name | `<pkg-name>` |
| Workflow filename | `publish-pypi.yml` |
| Environment name | `pypi` |

**Verify it saved.** After submit, the publisher must appear under **Manage current publishers**. If that list still says "No publishers are currently configured", the save silently failed — re-enter the form. This is the most common cause of `invalid-publisher: Publisher with matching claims was not found` errors on tag push, even when PyPI shows the package existing.

If a tag already failed to publish because trusted-publishing was missing, just `gh run rerun <id>` after configuring — no retag needed.
