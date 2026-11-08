---
description: |
  [TOPIC] Version Control Management
  [DETAILS] Plan source integration, version selection, publication and host adoption as distinct stages. Follow the leaf-owned release flow, preserve unrelated work and immutable tags, inspect CI for the candidate commit, and verify published artifacts before rollout. Use when reviewing branch hygiene or coordinating package versions; this skill does not replace the canonical release procedure.
tags: [scitex-general-development-version-control]
---

# SciTeX Version Management (Core Workflow)

Use this skill to establish scope and inspect version state. The
[current end-to-end release flow](18_end-to-end-release-flow.md) owns the release
sequence, authorization boundaries and publisher setup. The
[release and pin doctrine](14_release-and-pin-doctrine.md) covers dependency
adoption. Follow the selected leaf's source-owned procedure rather than copying
one package's workflow into another.

## Version Management Levels

Treat these as separate acceptance stages, not an automatic command chain.

| Stage | Scope | Evidence |
|-------|-------|----------|
| Source | Owned checkout and ordinary PR | Preserved work, reviewed diff and every check for the candidate commit |
| Release candidate | Canonical unused version and immutable tag | Accepted commit, complete declared profile and native validation |
| Publication | Declared package index and release record | Qualified wheel/sdist identity and successful actual publisher |
| Hosts | Authorized target services | Compatible installed packages, runtime health and relevant behavior |
| Skills | Exported agent-readable knowledge | Installed source/version binding, exported content and actual discovery where checked |

A higher stage does not follow merely because the previous command exited zero.
A pushed tag, index entry, healthy process or exported file each establishes only
its own observation. Identify which stages the user authorized and which have
actually been verified.

## How to Present Choices

Report the current source SHA, version source, latest applicable accepted tag,
publication evidence and host adoption separately. Explain the proposed scope
and any missing acceptance. Honor explicit standing authorization; do not ask
for the same permission again because a historical numbered menu said to wait.
If scope is missing, prepare a concrete reviewable candidate before clarifying.

## Preflight: respect the working tree

Before pull, checkout, install, release or rollout, inspect the actual target's
uncommitted changes, branch, tracking reference and remote state. Use an owned
worktree when other work is present. Follow
[version-control preflight](16_version-control-preflight.md); never discard,
stash or commit another agent's work as an automatic cleanup step.

## Pre-Push CI Check

Inspect all check runs, workflow runs and commit statuses for the exact
candidate SHA, including consent and security outcomes. Recent unrelated green
runs and the branch's required-check subset are not complete acceptance.
Replace placeholders with the selected repository and run:

```bash
gh pr view PR_NUMBER --repo scitex-ai/PACKAGE --json headRefOid,statusCheckRollup
gh pr checks PR_NUMBER --repo scitex-ai/PACKAGE
gh run view RUN_ID --repo scitex-ai/PACKAGE
```

Preserve failed or unavailable evidence. Do not force reruns, synthesize a
verdict or reduce the install/test profile to obtain a green result.

## Ecosystem Roster

Discover packages and providers in the current environment through Dev's
existing dispatcher. Do not maintain a second package count or assume that a
registered provider is installed, enabled or live. Distinguish a source checkout
from its installed distribution and the package actually serving a host.

## Should We Increment?

Inspect the diff since the applicable accepted release, not merely the nearest
tag of any kind. Determine whether public behavior, interfaces, dependencies,
packaged skills or bundled docs need delivery. Documentation-only work can
require a release when installed users need the corrected content.

### Minor vs Patch

| Bump | Typical scope |
|------|---------------|
| Patch | Compatible fixes and small corrections |
| Minor | Compatible public features or interfaces |
| Major | Breaking changes under the user's authorized scope |

Review the actual change and the owning package's version policy. A commit
prefix alone cannot determine compatibility or select a safe version.

### Also: did consumers grow a new minimum?

When a consumer starts using a new provider API, inspect its declared bounds
and normal dependency resolution. Raise a required minimum in the owning
consumer when justified. An upstream release alone does not prove that every
consumer can adopt it; preserve compatible qualified versions until the
replacement's complete profile passes.

## Version Increment (Core Workflow)

Inspect whether the leaf uses a literal version, setuptools-scm or another
source. Do not edit both `pyproject.toml` and `__init__.__version__` by rote.
Select an unused canonical version, integrate accepted source normally and
follow [the release flow](18_end-to-end-release-flow.md). Push only the intended
version tag after its commit is accepted. Tag creation is not publication.

## When to merge `develop` → `main`

Read the selected leaf's actual release workflow and protected-branch policy.
Do not assume that a tag pushed on `develop` advances `main` automatically.
Promote through the ordinary release PR and inspect all acceptance for the candidate commit;
no administrative bypass, auto-merge or alternate publication route.

## RULES: Never Sync Blind

- Inspect remote state before pushing and local changes before pulling.
- Preserve unrelated edits and unsuccessful qualification evidence.
- Classify artifacts against source ownership before removing anything.
- Record source, installed package and live-host identities separately.

## PyPI Trusted Publisher

Use the publisher declared by the leaf's actual repository, workflow and
environment. PyPI supports pending Trusted Publishers for new projects; a
manual first upload is not required. Setup and its official reference are in
[the canonical release flow](18_end-to-end-release-flow.md#pypi-trusted-publisher-setup-one-time-per-package).
A publisher error does not authorize a manual uploader or a moved tag.

## Troubleshooting

### Tag not reachable from current branch

Inspect the tag's actual commit and the selected branch history. A pushed tag
is immutable: do not delete, recreate or force-push it to another commit.
Preserve its qualification result. Repair source and select a new unused
version through the normal release procedure when a replacement is needed.

### Merge conflicts on remote hosts

Read the target's actual diff and preserve its work before resolving a merge
in an owned checkout. Do not run a blanket stash/pull/pop on a live authority
checkout or assume that historical host aliases still identify the target.
Qualified source integration and service rollout remain separate operations.

### Stale dist-info

Identify the interpreter and distribution actually imported before changing an
environment. Compare a fresh normal compatible installation with its wheel
metadata and installed RECORD. Do not delete guessed `*.dist-info` paths from a
shared environment to make an inconsistency disappear.
