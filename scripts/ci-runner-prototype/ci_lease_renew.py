#!/usr/bin/env python3
"""Auto-renewal cron for the CI-dedicated SLURM lease.

Polled by `scitex-dev cron` (or any cron on the operator host).
Resubmits the CI lease ~1 day before walltime expiry so the persistent
self-hosted GitHub runner never has a gap. SCOPE: the CI-dedicated lease
ONLY. Never touches the operator's other compute leases.

Operator-host config (production layout):
  ~/.scitex/dev/ci-runner.yaml — see ci-runner.yaml.example in this dir.

Mechanism:
  ssh <hpc_host> 'squeue -u <user> --name=<jobname> --noheader -o "%i %T %M %L"'
  → list current CI leases (by NAME, never by jobid — jobids cycle).
  Parse: pick the lease with the most time_left.
  If max(time_left) < renew_threshold AND no PENDING successor in the
  squeue listing → ssh <hpc_host> 'sbatch <sbatch_script>'.
  Log the action; on submit failure, exit non-zero so cron-mailer
  surfaces the alert.

Prototype-mode: in this branch it runs as a one-shot script, no daemon.
Productionization: proj-scitex-dev wraps the same logic as
`scitex-dev cron register ci-lease-auto-renew`.
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

CFG_PATH = Path.home() / ".scitex" / "dev" / "ci-runner.yaml"


def _load_cfg() -> dict:
    """Loads + validates the config. Caller bears the "no defaults" rule:
    each required key MUST be present in ~/.scitex/dev/ci-runner.yaml; the
    no-memory principle says "one config file, never guess from defaults".
    """
    if not CFG_PATH.exists():
        raise SystemExit(
            f"missing private config at {CFG_PATH}; "
            f"copy scripts/ci-runner-prototype/ci-runner.yaml.example and "
            f"fill in your bindings"
        )
    import yaml  # type: ignore[import-not-found]

    with CFG_PATH.open() as fh:
        cfg = yaml.safe_load(fh) or {}
    required = [
        ("hpc", "user"),
        ("hpc", "ssh_host"),
        ("ci_lease", "jobname"),
        ("ci_lease", "sbatch_script"),
        ("ci_lease", "renew_threshold_min"),
    ]
    for path in required:
        node = cfg
        for k in path:
            if not isinstance(node, dict) or k not in node:
                raise SystemExit(f"missing config key: {'.'.join(path)}")
            node = node[k]
    return cfg


def _parse_slurm_dhms(s: str) -> int:
    """Parse SLURM `[D-]HH:MM:SS` / `MM:SS` to minutes."""
    s = s.strip()
    days = 0
    if "-" in s:
        d, s = s.split("-", 1)
        days = int(d)
    parts = list(map(int, s.split(":")))
    if len(parts) == 3:
        h, m, _sec = parts
    elif len(parts) == 2:
        h, m = 0, parts[0]
    else:
        return 0
    return days * 24 * 60 + h * 60 + m


def _ssh_squeue(cfg: dict) -> list[dict]:
    target = f"{cfg['hpc']['user']}@{cfg['hpc']['ssh_host']}"
    cmd = [
        "ssh",
        "-o",
        "ControlPath=none",
        "-o",
        "ControlMaster=no",
        target,
        "/apps/slurm/latest/bin/squeue",
        "-u",
        cfg["hpc"]["user"],
        "--name=" + cfg["ci_lease"]["jobname"],
        "--noheader",
        "-o",
        "%i %T %M %L",
    ]
    out = subprocess.check_output(cmd, text=True, timeout=30)
    rows = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        rows.append(
            {
                "jobid": parts[0],
                "state": parts[1],
                "time_used_min": _parse_slurm_dhms(parts[2]),
                "time_left_min": _parse_slurm_dhms(parts[3]),
            }
        )
    return rows


def _ssh_sbatch(cfg: dict) -> str:
    target = f"{cfg['hpc']['user']}@{cfg['hpc']['ssh_host']}"
    cmd = [
        "ssh",
        "-o",
        "ControlPath=none",
        "-o",
        "ControlMaster=no",
        target,
        "cd ~ && /apps/slurm/latest/bin/sbatch "
        "--output=./slurm_logs/%j.out --error=./slurm_logs/%j.err "
        + cfg["ci_lease"]["sbatch_script"],
    ]
    out = subprocess.check_output(cmd, text=True, timeout=30)
    m = re.search(r"Submitted batch job (\d+)", out)
    if not m:
        raise RuntimeError(f"sbatch: unexpected output {out!r}")
    return m.group(1)


def main() -> int:
    cfg = _load_cfg()
    rows = _ssh_squeue(cfg)
    running = [r for r in rows if r["state"] == "RUNNING"]
    pending = [r for r in rows if r["state"] == "PENDING"]

    print(
        f"[ci_lease_renew {dt.datetime.now().isoformat()}] "
        f"running={len(running)} pending={len(pending)}"
    )

    if not running:
        print("[ci_lease_renew] no RUNNING CI lease; submitting")
        new = _ssh_sbatch(cfg)
        print(f"[ci_lease_renew] sbatch jobid={new}")
        return 0

    max_left = max(r["time_left_min"] for r in running)
    threshold = cfg["ci_lease"]["renew_threshold_min"]
    print(f"[ci_lease_renew] max time_left = {max_left} min (threshold {threshold})")
    if max_left > threshold:
        print("[ci_lease_renew] above threshold; nothing to do")
        return 0
    if pending:
        print("[ci_lease_renew] successor already PENDING; nothing to do")
        return 0

    print("[ci_lease_renew] threshold tripped + no successor; submitting")
    new = _ssh_sbatch(cfg)
    print(f"[ci_lease_renew] sbatch jobid={new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
