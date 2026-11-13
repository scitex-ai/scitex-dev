# Owned temporary context for release jobs

`scitex-dev` ships `scitex_dev/ci/owned_context.sh` as a Bash resource for
Linux release drivers. It supplies temporary-directory ownership, bounded
cleanup and cancellation of the driver's child process group. The leaf package
owns its release inputs, private HOME and caches, database refusal settings,
environment filtering and runner admission.

Use a dedicated Bash process with `set -euo pipefail`. Resolve the resource
with the same installed Python environment used by the release driver:

```bash
resource="$(python -c 'from importlib.resources import files; print(files("scitex_dev.ci").joinpath("owned_context.sh"))')"
source "$resource"
owned_context_init /absolute/existing/writable/scratch scitex-example-

driver_body() {
    # Configure leaf-owned private state inside "$OWNED_TMPDIR" here.
    # Run the actual build/test/probe synchronously; reap its descendants.
    ./release-probe.sh
}
run_owned_body
```

The parent directory must exist, be writable and resolve to an absolute path
other than `/`. The label starts with a lowercase letter, contains only
lowercase letters, digits, underscores and hyphens, and ends with a hyphen.
Initialization creates a mode-0700 directory with a six-character random suffix
and exports its path as `TMPDIR`. Source and initialize once per dedicated shell.

The resource installs EXIT, INT and TERM traps. It preserves a nonzero body
exit code; a cleanup failure converts an otherwise successful exit to failure.
INT and TERM cancel the registered child group using its kernel birth token,
with a two-second escalation watchdog, and return 130 and 143 respectively.
The group must disappear before cleanup. Background work must be joined by the
body; a surviving group causes refusal and retains scratch.

Cleanup checks the original root's device, inode, owner and mode, rejects a
symlink or replacement, surveys its filesystem without crossing devices, then
rechecks identity immediately before removal. The fixed survey bound is ten
seconds. Removal uses these existing reviewed capacity classes:

| Maximum entries | Maximum allocated bytes | Removal bound |
| --- | --- | --- |
| 10,000 | 1,073,741,824 (1 GiB) | 10 seconds |
| 200,000 | 34,359,738,368 (32 GiB) | 60 seconds |

Both limits must fit a row. An unavailable survey or larger tree is retained
with an error. These are cleanup bounds, separate from product test deadlines.
Consumers must qualify their actual full dependency profile against the bounds.

The resource requires Linux `/proc`, Bash job control and GNU coreutils/find
at their standard `/usr/bin` paths. It is an internal CI resource, without a
new public CLI verb. It does not admit a runner, authenticate a publisher,
verify an image, sanitize a child environment or isolate a release from ambient
services. A leaf adapter must supply and test those contracts independently.
