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

`ci runner validate-policy --json` is read-only. It verifies all three CPU
registrations are online and assigned to group 6, Organization. That group
must retain organization repository availability while restricting access
to exactly seven reviewed reusable workflows at one full commit revision.
The validator fetches those seven definitions and their same-revision
hosted admission workflow and checks all eight reviewed byte hashes.
This permits normal source merges without accepting unreviewed workflow
changes. Unknown or incomplete API/source observations exit nonzero.

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
