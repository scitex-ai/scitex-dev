---
name: interface-cli-exit-codes
description: SciTeX CLI exit code semantics — 0 success, 1 runtime, 2 usage, 3-9 domain, ≥10 reserved.
user-invocable: false
tags: [scitex-python, scitex-general, cli]
---

# §3. Exit codes

| Code  | Meaning                                                  |
|-------|----------------------------------------------------------|
| `0`   | Success                                                  |
| `1`   | Generic runtime error                                    |
| `2`   | Usage error (bad flags, missing arg, precondition unmet) |
| `3-9` | Domain-specific (document in `--help`)                   |
| `≥10` | Reserved for signal translation / shell conventions      |
