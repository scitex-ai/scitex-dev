# Release-fixture device observations

The repository-only release-command observer samples the original owned
fixture's filesystem after finding one caller-thread child candidate. Its
`fixture_filesystem.device_io` records shared block-device context; it does
not authenticate the candidate or diagnose why a command stalled.

`tests/integration/_release_device_observation.py` decodes that fixture's
`st_dev` with `os.major` and `os.minor` and reads its numeric sysfs `dev`/`stat`
attributes. This matters when a container's `/tmp` is backed by a different
device from the host's `/tmp`. It never substitutes the host path's device.

The recognized input is the kernel's current 17-field block statistics layout.
It returns read/write completion counts, cumulative read/write wait milliseconds,
in-flight requests, active milliseconds and weighted milliseconds. Field meanings
follow the [kernel block statistics documentation](https://docs.kernel.org/block/stat.html).
In-flight is a gauge; the other returned values are cumulative. One record is
not a baseline/delta or a per-process measurement. Device and backing-device
records are not atomic together and can include unrelated workloads.

The reader covers at most four direct backing devices, with no recursion. A
backing partition is not a full physical-device topology. A valid primary
record can have `direct_backing.state = unknown`; that does not mean no backing
activity. Each attribute read is limited to 64 bytes (`dev`) or 1,024 bytes
(`stat`), with a one-byte over-limit probe. Only bounded unsigned numeric
fields are returned. Final attribute symlinks and nonregular files are refused;
normal sysfs directory links remain supported. Device identity is rechecked
around the reads. Missing, malformed, oversized or unsupported data remains
unknown instead of becoming zero. Raw names, serials, paths and input text are
not included in this added context.

These are byte/count bounds, not a guarantee that kernel operations complete
within a deadline. Collection remains on the existing background thread. Its
24-sample cap, one-second initial wait, quarter-second interval and quarter-second
close/join remain unchanged; incomplete collection stays explicit. The original
five-second subprocess call, timeout exception, PID/cwd checks, process cleanup,
runner/admission settings and filesystem durability policy are unchanged.

Controls use actual owned temporary files and the real observer in
`tests/integration/test_ci_release_device_observation.py`. Existing command and
child isolation controls remain in `test_ci_release_command_diagnostics.py`.
No failed release fixture needs to be replayed to validate the parser. Static
observations or passing controls do not qualify a failed candidate, publisher,
release image or live deployment.
