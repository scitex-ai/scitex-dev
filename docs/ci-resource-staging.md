# Internal CI resource staging

The internal helper `src/scitex_dev/ci/_stage_resource.py` stages a downloaded
resource into an existing caller-owned directory with mode 0700. It verifies
the caller's expected SHA-256, rejects symlink and non-regular source files,
limits input to 1 MiB, and creates the destination exclusively with mode 0600.
An occupied destination is preserved. The internal CLI is silent on success;
the Python helper returns a path/hash/size receipt to programmatic callers.

The shared caller must obtain the expected digest from its reviewed source
contract, download the pinned source, and own the staging directory's lifecycle.
The helper verifies byte transport. It does not decide which resource is trusted
or admit a runtime, release tag, publisher or package.

The filesystem controls exercise the real Dev-owned lifecycle resource through
an isolated Python CLI and refuse tampered input, unsafe source types, occupied
destinations and unsafe destination parents. This helper is internal; it adds no
public SciTeX command. Automatic adoption by shared release callers is separate.
