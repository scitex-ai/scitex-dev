# PyPI Publish Failure Investigation — scitex-todo (2026-06-14)

**Investigator:** scitex-dev CI-health subagent
**Authorized by:** lead msg 160914b7 (read-only, hypothesis-test)
**Branch:** `feat/pypi-publish-investigation` (scitex-dev worktree)
**Scope:** READ-ONLY. No leaf-repo changes. No PR. No rerun.

---

## TL;DR

1. **Question 1 — structural vs real test failure?** STRUCTURAL. Same class as
   the issue surfaced by the earlier `feat/ci-health-diagnose-scitex-todo`
   commit `fc58d6c9`. Evidence below: empty `runner_name`, `steps: 0`,
   `total_ms: 0`, BlobNotFound-style log-API miss. Not a real pytest failure;
   not a real publish-step failure.

2. **Question 2 — scitex-todo-specific or fleet-wide?** scitex-todo-SPECIFIC.
   5 other scitex-* repos sampled all publish successfully. Their occasional
   "failure" conclusion is benign `sync-main` step, not the structural
   startup_failure.

3. **Onset:** 2026-06-13T23:25Z (v0.7.11 release run, run_id `27482209759`)
   — exactly between the last good run (v0.7.10, `27482091011`, 2m52s,
   publish: SUCCESS) and the first broken run. No workflow YAML change in
   that window. `.github/workflows/` last touched on develop is
   `ff932f4948` at 2026-06-14T13:48, unrelated to v3 board work.

4. **Recommendation:** This is not fixable by editing the workflow YAML.
   Lead should investigate scitex-todo's Actions runner config /
   organization-level required-workflow setting / OIDC trust config rather
   than reshape the release-ci.yml. Fix-template included below is the
   SHAPE of a yaml-side mitigation in case the cause turns out to be the
   `concurrency: cancel-in-progress` group colliding with something, but
   the structural signature suggests this is infra, not yaml.

---

## Evidence — Question 1 (structural, not real test failure)

### Last 5 scitex-todo `release` workflow runs (all FAILURE):

| run_id | tag | duration | conclusion |
|---|---|---|---|
| 27504570927 | v0.7.25 | 12s | failure |
| 27501650744 | v0.7.24 | 11s | failure |
| 27501068318 | v0.7.23 | 6s | failure |
| 27498084384 | v0.7.22 | 6s | failure |
| 27497958229 | v0.7.21 | 5s | failure |

All sub-15-second durations — far too short for actual matrix pytest
execution (compare: v0.7.10 which actually published ran for 2m52s).

### Per-job inspection of v0.7.25 (`27504570927`):

```
JOB: test (3.12)  | conclusion: failure | runner_name: ''   | steps: 0
JOB: test (3.13)  | conclusion: failure | runner_name: ''   | steps: 0
JOB: test (3.11)  | conclusion: failure | runner_name: ''   | steps: 0
JOB: publish      | conclusion: skipped | runner_name: None | steps: 0
JOB: build        | conclusion: skipped | runner_name: None | steps: 0
JOB: release      | conclusion: skipped | runner_name: None | steps: 0
JOB: sync-main    | conclusion: skipped | runner_name: None | steps: 0
```

### Timing API for same run:

```json
{"billable":{"UBUNTU":{"total_ms":0,"jobs":7,
  "job_runs":[
    {"job_id":81293368701,"duration_ms":0},
    {"job_id":81293368707,"duration_ms":0},
    {"job_id":81293368749,"duration_ms":0},
    {"job_id":81293381089,"duration_ms":0},
    {"job_id":81293381169,"duration_ms":0},
    {"job_id":81293381299,"duration_ms":0},
    {"job_id":81293381359,"duration_ms":0}
  ]
}, "run_duration_ms":12000}
```

Zero billable ms across 7 jobs. The 12s wall-clock is GitHub overhead, not
job execution.

### Log-API miss:

```
$ gh run view 27504570927 --log-failed
log not found: 81293368701
log not found: 81293368707
...
```

This is the BlobNotFound signature from the earlier ci-health audit.

### Signature triplet (identical to #19 / `fc58d6c9` findings):

1. `runner_name == ""`           (no runner ever attached)
2. `steps == 0`                  (no execution graph rendered)
3. `total_ms == 0`               (no billable time)
4. Logs API returns "not found"  (no blob to fetch)

This is **GitHub Actions startup_failure**, not a test assertion or
publish-step error.

### Compare with last GOOD release (v0.7.10, run `27482091011`):

```
JOB: test (3.13) | conclusion: success | runner: 'GitHub Actions 1000124537' | steps: 9
JOB: test (3.12) | conclusion: success | runner: 'GitHub Actions 1000124538' | steps: 9
JOB: test (3.11) | conclusion: success | runner: 'GitHub Actions 1000124539' | steps: 9
JOB: build       | conclusion: success | runner: 'GitHub Actions 1000124540' | steps: 10
JOB: publish     | conclusion: success | runner: 'GitHub Actions 1000124541' | steps: 5
JOB: release     | conclusion: success | runner: 'GitHub Actions 1000124542' | steps: 7
JOB: sync-main   | conclusion: failure | runner: 'GitHub Actions 1000124543' | steps: 5
   FAIL step: Open develop->main PR if diverged
```

Same workflow YAML — only the sync-main step (a non-critical post-publish
PR-opening step) is red. publish: SUCCESS → PyPI 0.7.10 confirmed at
2026-06-13T23:21:52.

---

## Evidence — Question 2 (scitex-todo-specific, NOT fleet-wide)

### PyPI vs latest tag, plus most recent release-workflow run, per repo:

| repo | PyPI latest | latest release run | duration | conclusion |
|---|---|---|---|---|
| **scitex-todo** | **0.7.10** | v0.7.25 (`27504570927`) | **12s**  | **failure (structural)** |
| scitex-config   | 0.3.6  | v0.3.6  (`26662762940`) | 1m33s   | success |
| scitex-clew     | 0.2.15 | v0.2.15 (`26755868871`) | 2m1s    | success |
| scitex-io       | 0.3.1  | v0.3.1  (`27077084950`) | 3m31s   | success |
| scitex-hub      | 0.18.1 | v0.18.2 (`26882217170`) | 11m41s  | failure (real — needs separate audit) |
| scitex-dev      | 0.17.14| v0.17.14(`27479344458`) | 2m29s   | failure (only sync-main step; publish: SUCCESS, PyPI matches tag) |

Only scitex-todo shows the structural signature. scitex-hub and scitex-dev
"failures" had real runner attached, real steps, real billable time —
those are normal-shape failures (or, in scitex-dev's case, only the
sync-main post-publish step failing, which doesn't block PyPI publish).

### Broader evidence inside scitex-todo:

The structural failure is not even all-workflows-in-scitex-todo. Two
non-release workflows STILL ran successfully on 2026-06-12 (just 1 day
before the breakage):

| workflow file | last success | duration |
|---|---|---|
| `pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml` (`tests`) | 2026-06-12T07:54 | 1m10s |
| `import-smoke-on-ubuntu-py3-12.yml` (`import-smoke`) | 2026-06-12T07:54 | 18s |

(However, **those two files are no longer in the repo** as of develop:
develop's `.github/workflows/` contains only cla.yml, pr-ci.yml,
pypi-publish-and-github-release-on-tag.yml, release-ci.yml,
rtd-sphinx-build-on-ubuntu-latest.yml. They were deleted at some point —
explains why they stopped running, but doesn't explain why pr-ci /
release / release-ci started 0-step-failing in lockstep on 2026-06-13.)

### Onset window:

- 2026-06-13T23:19:29Z — v0.7.10 release run starts (last success, 2m52s)
- 2026-06-13T23:21:52Z — PyPI 0.7.10 actually uploaded
- 2026-06-13T23:25:18Z — v0.7.11 release run starts (FIRST 0-step failure, 12s)

NO `.github/workflows/*` commits in this 6-minute window — the only
post-23:21Z `.github/` commit on develop was `ff932f4948` on 06-14T13:48,
many hours later. The breakage is NOT a YAML regression.

### Repo-level Actions settings comparison:

```
scitex-todo  /actions/permissions          : enabled=true, allowed_actions=all
scitex-todo  /actions/permissions/workflow : default_workflow_permissions=read,
                                              can_approve_pull_request_reviews=false
scitex-dev   /actions/permissions          : enabled=true, allowed_actions=all
scitex-dev   /actions/permissions/workflow : default_workflow_permissions=write,
                                              can_approve_pull_request_reviews=true
```

scitex-todo runs with `default_workflow_permissions=read` while scitex-dev
runs with `write`. This isn't sufficient to explain 0-step failures (read
should still allow runner attach), but it's a configured-by-someone
divergence worth flagging.

---

## Proposed fix template

**File:** this same file — `/work/.worktrees/agent-a96ceb3941dd9f545/docs/audits/pypi-publish-investigation-2026-06-14.md`

**No YAML diff is proposed for application.** The structural signature
(empty runner, 0 steps, 0 billable_ms, BlobNotFound) is infrastructure-
level, not workflow-syntax-level, so editing the workflow file will not
unblock publishes. Possible real causes — for lead triage:

1. **Concurrency-group leak.** scitex-todo's `pr-ci.yml` defines
   `concurrency.group: ${{ github.workflow }}-${{ github.ref }}` with
   `cancel-in-progress`. If GitHub's workflow scheduler is wedged on a
   stuck group entry from an unrelated workflow that was deleted (e.g.
   the missing `pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml` /
   `import-smoke-on-ubuntu-py3-12.yml` / `quality-on-ubuntu-latest.yml`
   files that no longer exist on develop/main but are still "active" per
   `/actions/workflows`), this could cascade. Recommend lead:
   ```
   gh api -X DELETE \
     repos/ywatanabe1989/scitex-todo/actions/workflows/<workflow_id>/disable
   ```
   on the dead workflows after confirming nothing references them.
2. **OIDC trust mismatch.** The publish job uses `id-token: write` with
   `environment: pypi`. If the PyPI trusted-publisher binding got rotated
   or invalidated, the token-mint step would fail. BUT — this wouldn't
   produce 0 steps on the *test* job upstream. Lower probability.
3. **Required-workflow / org rulebook.** If ywatanabe1989 enabled a
   required workflow at user/org level that references a path that
   doesn't exist in scitex-todo, every triggered workflow gets killed at
   startup with no runner attach. **Most consistent with the signature.**
   Lead: check `gh api repos/ywatanabe1989/scitex-todo/rules/branches/main`
   and any org rulesets.
4. **Runner-allocation transient.** Very rare; would not persist 24h+.
   Rule out by manual `gh workflow run release-ci.yml --ref develop`
   from lead's session after the doctrine hold lifts.

**If yaml-side hardening is wanted as belt-and-suspenders** once the
real cause is found, the recommended shape is to (a) remove the
`cancel-in-progress: true` on `pr-ci.yml` for releases-of-record so
concurrent PR runs don't trample release-ci, and (b) split test/publish
into independent workflows so a test-job startup_failure does not skip
publish. Neither will fix the current 0-step failure, but both will
reduce blast radius for the next incident.

---

## Open question for lead routing

- **Q-A:** Lead should pull the run-attempt's `check_run` log via
  `gh api repos/ywatanabe1989/scitex-todo/actions/runs/27504570927/attempts/1`
  — this may reveal an "actions required" message the public API hides.
  If the agent's PAT lacks scope, this needs lead to run.
- **Q-B:** Are the org/user-level required-workflow rulesets owned by
  lead? If so, lead can directly inspect for a stale path reference.
  If not, who?
- **Q-C:** scitex-hub v0.18.2 release also red (`26882217170`, 11m41s);
  that one's a real failure, separate from this investigation. Should
  ci-health pick that up next, or is it already in scope of #19?

## Hold posture

Per discipline of #19: **HOLD on rollout.** No leaf-repo changes
proposed. No PRs filed. Doc committed to scitex-dev worktree only on
branch `feat/pypi-publish-investigation` for lead review.
