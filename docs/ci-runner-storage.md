# Local CI runner storage

Local organization runners must keep their entire runner home on the host's
capacity filesystem. Moving only `TMPDIR` is insufficient: GitHub Actions also
writes job diagnostics to `_diag`, checkouts to `_work`, and tool downloads to
`_tool`.

Inspect without mutation:

```bash
scitex-dev ci runner relocate-storage \
  --source "$HOME/actions-runner-org" \
  --destination "/scratch/$USER/ci/actions-runner-org"
```

Apply only while the runner is idle:

```bash
scitex-dev ci runner relocate-storage \
  --source "$HOME/actions-runner-org" \
  --destination "/scratch/$USER/ci/actions-runner-org" \
  --apply
```

The operation stops the user service, copies and verifies the runner, switches
the established home path to a symbolic link, restarts and health-checks the
service, and rolls back on failure. Agent services are not touched.
