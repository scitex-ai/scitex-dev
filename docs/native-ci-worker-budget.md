# Dev native CI worker budget

`.github/ci/run-in-sif.sh` runs this checkout's complete `.[all,dev]` test
environment inside the registered immutable image. It starts its own
socket-only PostgreSQL cluster and retains coverage, all tests, `--dist load`,
and the existing cleanup and kernel deadlines.

Each matrix job defaults to at most four pytest-xdist workers. Hosts may run
several runner services at once, so `nproc` does not establish exclusive CPUs
for one job. `CI_XDIST_WORKERS` may request an integer from 1 through 4. The
selected count is reduced by the process's actual CPU affinity and a visible
cgroup v2 `cpu.max` or v1 CFS quota. A fractional CPU quota admits one worker;
invalid configuration or malformed quota data fails rather than running an
unbounded job. The driver logs its resolved worker count.

`tests/integration/test_ci_worker_budget.py` executes the actual shell block,
including a subprocess constrained to one real CPU, and checks invalid worker
configuration. Run local checks through the existing release context with an
owned, nonsymlinked temporary directory; symlinked capability paths remain
forbidden.

Source-hash admission is separate from local qualification. Changing this
worker policy changes the registered driver bytes. Native GitHub execution
must remain refused until the central source registry reviews that exact
successor. The Dev runner observer's hypothetical source replay does not grant
admission, execute jobs, or publish a release.
