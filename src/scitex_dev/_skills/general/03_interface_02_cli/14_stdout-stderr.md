---
name: interface-cli-streams
description: SciTeX CLI stdout/stderr discipline — stdout for data/JSON, stderr for logs. `cmd --json | jq ...` must work uncontaminated.
user-invocable: false
tags: [scitex-python, scitex-general, cli]
---

# §8. stdout vs stderr

- **stdout** — data, JSON, parseable output. Pipe-friendly.
- **stderr** — logs, progress, warnings, errors.
- A user must be able to `cmd --json | jq ...` with zero log contamination on stdout.
