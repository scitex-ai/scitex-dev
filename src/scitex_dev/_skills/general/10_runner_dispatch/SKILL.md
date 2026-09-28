---
name: runner-dispatch-recovery
description: |
  [WHAT] Diagnose and recover GitHub self-hosted runner dispatch stall for the SciTeX fleet: jobs queue forever while runners report online+idle. Covers the full isolation ladder (labels, sessions, network, registration, org group flags) and the root causes found 2026-09-28.
  [WHEN] Any queued-forever self-hosted job with idle matching runners, after any runner re-provisioning, or when fleet CI goes silent.
  [HOW] Follow the ladder below in order; each step rules out one layer. Do not skip to re-registration before ruling out config.
tags: [scitex-fleet-ci, github-actions]
user-invocable: false
primary_interface: mixed
interfaces:
  python: 0
  cli: 3
  mcp: 0
  skills: 0
  http: 0
---

# Runner dispatch recovery

Measured 2026-09-28 (7-day stall, 4 repos). Jobs queued with matching
online+idle runners; root causes were TWO compounding faults.

## Fault 1 (fatal): org runner group barred public repos

`GET /orgs/{org}/actions/runner-groups/1` showed
`allows_public_repositories: false` while every fleet repo is PUBLIC.
Public-repo jobs can never use such a group and queue forever with zero
diagnostic (empty check output, no runner offer in logs).

Fix: `PATCH` the group with a JSON boolean
(`echo '{"allows_public_repositories":true}' | gh api -X PATCH
orgs/{org}/actions/runner-groups/1 --input -`). Note `-f` sends a STRING
and fails 422; `--input -` sends real JSON.

## Fault 2 (latent): stale/corrupt registrations after re-provisioning

Signs: `TaskAgentSessionConflictException` / "session already exists" in
`_diag/Runner_*.log` right after restarts; duplicate/conflicting sessions.
Fix: stop service, server-side `DELETE
orgs/{org}/actions/runners/{id}`, local `./config.sh remove
--unattended --token $REM`, fresh `./config.sh --unattended --url ...
--name <unified-name> --labels ... --runnergroup Default --work _work`,
start service. Use unified names (`scitex-ci-02/03/04`,
`scitex-docker-03`); delete stray registrations (e.g. mystery `ci-05`)
and unused groups.

## Isolation ladder (in order)

1. **Labels exact?** Compare job `labels[]` (jobs API) vs runner
   `labels[]` (runners API). Subset match required.
2. **Runners genuinely online?** Stop one 2 min; API must flip to
   offline. If not, status is stale.
3. **Network?** `curl https://broker.actions.githubusercontent.com/`
   must return fast with valid TLS from each host.
4. **Registration healthy?** Fresh `Runner_*.log` reaches "Listening for
   Jobs" without session Conflict. Conflict storm after restart =
   duplicate process or lingering server session; wait 3 min, else
   delete + re-register.
5. **Personal-repo probe (decisive).** Register a runner to a PRIVATE
   personal repo with a unique label and dispatch. Works there + fails
   in org = org-scoped fault, hosts exonerated.
6. **Org group flags.** Read every runner group object fully:
   `visibility`, `allows_public_repositories`, `restricted_to_workflows`.
   Compare against repo visibility (public repos need the flag true).
7. **Fresh probe after each change.** `workflow_dispatch` a real job;
   queued jobs created before a fix may never re-evaluate — always test
   with a NEW run. Cancel stale queues to reduce noise (re-runnable).

## Group design (fleet convention 2026-09-28)

- `Default`: GitHub-hosted runners only.
- `Organization`: all fleet self-hosted runners (visibility all +
  `allows_public_repositories: true`, required since fleet repos are public).
- `ywatanabe1989`: personal experiments.
- Workflows target the Organization group implicitly via labels today;
  explicit `runs-on: {group: Organization}` is the follow-up.

## Hygiene after recovery

- No stray registrations, no empty groups, unified names.
- Debug: org variables `ACTIONS_RUNNER_DEBUG=true`
  + `ACTIONS_STEP_DEBUG=true` (org variables, visibility all).
- Verify with a dispatched probe run to `in_progress` on a named runner
  before declaring victory.
