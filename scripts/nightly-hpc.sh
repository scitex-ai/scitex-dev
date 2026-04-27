#!/usr/bin/env bash
# Nightly HPC dispatch: rsync heavy packages to remote, run pytest on a
# compute node via scitex-hpc, summarise results.
#
# This script is generic. All site-specific values (host, partition, package
# list, cron time) live in ~/.scitex/hpc/config.yaml.
#
# Install:
#   crontab -e
#   # use the hour/minute from ~/.scitex/hpc/config.yaml
#   0 3 * * *  /home/<you>/proj/scitex-dev/scripts/nightly-hpc.sh \
#                 >> /home/<you>/proj/scitex-dev/logs/nightly-hpc.log 2>&1

set -euo pipefail

CONFIG="${SCITEX_HPC_CONFIG:-${HOME}/.scitex/hpc/config.yaml}"
[[ -f "${CONFIG}" ]] || {
    echo "missing ${CONFIG}" >&2
    exit 2
}

REPO_DEV="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${REPO_DEV}/logs"
STAMP=$(date +%Y%m%d-%H%M%S)
RESULTS="${LOG_DIR}/nightly-${STAMP}"
mkdir -p "${RESULTS}"

# Sync each heavy package to the configured host.
echo "[$(date)] Syncing heavy packages..."
SCITEX_HPC_CONFIG="${CONFIG}" python3 - <<'PY'
import os, sys, yaml
from pathlib import Path
from scitex_hpc import JobConfig, sync

cfg = yaml.safe_load(open(os.environ["SCITEX_HPC_CONFIG"]))
host = cfg["host"]
proj_root = Path.home() / "proj"
failed = []
for pkg in cfg.get("heavy_packages", []):
    src = proj_root / pkg
    if not src.exists():
        print(f"skip {pkg}: not found at {src}")
        continue
    jc = JobConfig(project=pkg, command="", host=host)
    if not sync(jc, local_path=str(src)):
        failed.append(pkg)
sys.exit(1 if failed else 0)
PY

# Dispatch tests on the remote compute node.
COVERAGE=1 FAST=0 \
    bash "${REPO_DEV}/scripts/test-heavy-hpc.sh" \
    2>&1 | tee "${RESULTS}/run.log"

# Optional Telegram summary (if scitex-notification is installed).
python3 - <<PY
import sys
try:
    import scitex_notification as nf
except ImportError:
    sys.exit(0)
fails = sum(1 for line in open("${RESULTS}/run.log") if line.startswith("FAILED:"))
msg = f"HPC nightly: {fails} failed packages" + (" ok" if fails == 0 else " warn")
nf.alert(msg, channel="dev")
PY
