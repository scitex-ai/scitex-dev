#!/usr/bin/env bash
# Nightly Spartan dispatch: run heavy SciTeX test suites on sapphire CPU nodes,
# upload JUnit + coverage to a results dir, and send a Telegram summary.
#
# Install: add to crontab on the dev box (e.g. ywata-note-win) with
#   crontab -e
# then add the line:
#   0 3 * * *  /home/ywatanabe/proj/scitex-dev/scripts/spartan-nightly.sh \
#                  >> /home/ywatanabe/proj/scitex-dev/logs/spartan-nightly.log 2>&1
#
# Why 03:00: outside Australian business hours; sapphire queue is shorter then.
# Why dev box (not GH Actions): SSH credentials to Spartan are local; no
# secrets need to leak to GitHub.

set -euo pipefail

REPO_DEV="/home/ywatanabe/proj/scitex-dev"
LOG_DIR="${REPO_DEV}/logs"
STAMP=$(date +%Y%m%d-%H%M%S)
RESULTS="${LOG_DIR}/spartan-${STAMP}"
mkdir -p "${RESULTS}"

# Sync local sources to Spartan first (rsync via scitex-dev sync).
echo "[$(date)] Syncing local sources to spartan..."
python3 -c "
from scitex_dev.sync import sync_host
from scitex_dev.config import load_config
cfg = load_config()
ok = sync_host(cfg, host_name='spartan')
import sys; sys.exit(0 if ok else 1)
" || {
    echo "sync to spartan FAILED — aborting nightly run" >&2
    exit 1
}

# Then dispatch each heavy package to sapphire.
COVERAGE=1 FAST=0 \
    bash "${REPO_DEV}/scripts/test-heavy-on-spartan.sh" \
    2>&1 | tee "${RESULTS}/run.log"

# Notify via Telegram (if scitex-notification is installed locally).
python3 -c "
import os, sys
try:
    import scitex_notification as nf
except ImportError:
    print('scitex-notification not installed; skipping Telegram')
    sys.exit(0)
fails = 0
with open('${RESULTS}/run.log') as f:
    for line in f:
        if line.startswith('FAILED:'):
            fails += 1
msg = f'Spartan nightly: {fails} failed packages' + (' ✅' if fails == 0 else ' ⚠️')
nf.alert(msg, channel='dev')
"
