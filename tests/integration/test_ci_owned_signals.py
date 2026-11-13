"""Cancel only a fixture-owned Bash body and verify its scratch is retired."""

import os
import signal
import subprocess
import time
from pathlib import Path

RESOURCE = Path(__file__).resolve().parents[2] / "src/scitex_dev/ci/owned_context.sh"


def birth(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()[19]
    except (FileNotFoundError, ProcessLookupError):
        return None


def cancel_fixture(parent, child, token):
    """Failure cleanup may signal only the exact child registered by this fixture."""
    if child is not None and token is not None and birth(child) == token:
        try:
            os.killpg(child, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if parent.poll() is None:
        parent.kill()
        parent.communicate(timeout=5)


def test_term_reaps_owned_body_before_cleanup(tmp_path):
    # Arrange
    ready = tmp_path / "ready"
    code = r'''set -euo pipefail
source "$1"
owned_context_init "$2" scitex-owned-signal-
driver_body() {
    printf '%s' "$BASHPID" > "${READY}.pending"
    mv "${READY}.pending" "$READY"
    sleep 30
    touch "$LATE"
}
export READY="$2/ready" LATE="$2/late-write"
run_owned_body
'''
    process = subprocess.Popen(
        ["bash", "-c", code, "owned-signal", str(RESOURCE), str(tmp_path)],
        env={"PATH": os.defpath, "HOME": str(tmp_path)},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True,
    )
    child = token = None
    try:
        until = time.monotonic() + 5
        while not ready.exists() and process.poll() is None and time.monotonic() < until:
            time.sleep(0.02)
        child = int(ready.read_text())
        token = birth(child)
        # Act
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=15)
        # Assert
        assert (process.returncode, list(tmp_path.glob("scitex-owned-signal-*")), (tmp_path / "late-write").exists()) == (143, [], False), (stdout, stderr)
    finally:
        cancel_fixture(process, child, token)
