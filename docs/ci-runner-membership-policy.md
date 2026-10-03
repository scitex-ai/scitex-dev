# Organization runner policy

The 2026-10-03 operator mandate keeps compute02/03/04 in the scitex-ai
organization pool. Personal repositories and external contributions use
GitHub-hosted CI. Labels select hardware; they confer no authorization.

`ci runner register` defaults CI_RUNS_ON to `["ubuntu-latest"]` using the
existing normal gh account. `ci runner use github --repo owner/repo`
creates or updates that variable and verifies its readback. Native opt-in
through `ci runner use self-hosted` requires an organization repository and
a qualified live group policy. No membership token or new credential is
created. The canonical caller passes its variable preference to the shared
workflow admission check, which verifies the original actor, triggering
actor, and same-repository PR author independently. Forks and unknown
membership remain hosted.

The canonical caller pins production revision
`8c646081e9f1352077d3d8674052cce7ec75a1b7`, qualified after the ordinary
organization source merge. It does not rely on a branch reference matching
a runner-group SHA selection. Source and caller pinning alone do not permit
a group policy switch: retained direct/custom jobs, required status names,
portable hosted environments and naturally draining old jobs need separate
qualification. In particular, a real immutable SIF/PostgreSQL test gate is
preserved until its protected reusable adapter and hosted equivalent qualify.

`ci runner validate-policy --json` is read-only. It observes the three CPU
registrations, the existing compute03 Docker registration and the additional
compute04 CPU registration. Reviewed group identities are nondefault group6
`Organization` and group8 `scitex-company-ci`; either must retain organization
repository availability and restrict workflow access. The current protected
main profile contains eleven reviewed reusable definitions plus their same
revision hosted admission. The historical ten-definition immutable profile
retains its original admission bytes and literal revisions separately.
This permits normal source merges without accepting unreviewed workflow
changes. Unknown or incomplete API/source observations exit nonzero.

The organization-owned `company-ci-pool-health` workflow also samples one
admitted runner every fifteen minutes or by manual dispatch. It reads visible
CPU counts, priority, memory, filesystem space and CPU pressure without a
checkout, credentials or package installation. One completed sample does not
qualify the entire pool or replace package CI. Its defining reusable must be
included in the live restricted selection before native execution.

The managed `ci-runner-policy` cron job runs this observation every fifteen
minutes. Its report separates present busy state from completed-job
timestamps. Completed jobs are sampled from the three latest public
scitex-dev CI runs; that bounded sample is explicitly not organization-wide.
Missing evidence has a null timestamp and age. Idle alone is neither a
completed-job claim nor a stopped-runner claim. The observation never
registers, starts, stops, moves, or reconfigures runners.

Source publication, group-policy readback, and actual job execution remain
distinct qualification steps. Older generic HPC/per-repository ensure
commands are not the deployment path for this organization-only pool.
