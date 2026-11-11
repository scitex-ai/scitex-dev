---
description: |
  [TOPIC] Interface Cli Pass Through
  [DETAILS] SciTeX CLI pass-through entry points — tool wrappers (`<cli> git ...`), script exec (`<cli> run script.py`), one-shot eval. Exempt from §1 noun-verb rule.
tags: [scitex-general-interface-cli-pass-through]
---

# §1c. Pass-through exceptions

Entry points that delegate a command tail to another tool. The wrapper must
preserve the downstream argument values and order, subject to its documented
option-separator handling; Click still processes its own parsing controls.

| Pattern           | Example                                       | Why                                      |
|-------------------|-----------------------------------------------|------------------------------------------|
| Tool pass-through | `<cli> git <anything>`, `<cli> uv <anything>` | Args handed to upstream binary unchanged |
| Script exec       | `<cli> run <script.py> -- <args>`             | `--` preserves downstream flag semantics |
| One-shot eval     | `<cli> eval "<code>"`                         | Body is opaque to the parser             |

## Rules

- **Must** be declared in `--help` (the description should say "passes args to `<tool>`" or equivalent).
- **Must not** rewrite or reorder forwarded arguments.
- Pass-through entry points are exempt from the §1 noun-verb rule.

## Declare the actual forwarding contract

The current auditor recognizes a Click command whose `context_settings` sets
both `ignore_unknown_options=True` and `allow_extra_args=True`. Declare this
only for a real forwarding boundary, and explain the delegation in help:

```python
import subprocess

import click


@click.group()
def cli():
    """Command-line tools."""


@cli.command(
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    help="Pass arguments to upstream git in their original order.",
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def git(args):
    raise SystemExit(subprocess.run(["git", *args], check=False).returncode)
```

For example, `cli git --version` invokes the installed `git --version` and
returns its status. Click consumes a standalone `--` option separator rather
than forwarding that token; test and document separator behavior when an
upstream command needs a literal separator. This example is not a complete
SciTeX root CLI or a declaration that every interface rule passes.

A module-level `PASS_THROUGH_COMMANDS` list is **not read by the current
auditor**. It does not exempt a command. Internally `_is_pass_through` also
recognizes the command object's `_pass_through` attribute; that private signal
is not a public registration API or evidence of correct forwarding. A variadic
`UNPROCESSED` argument alone does not satisfy the context-settings detector.
Do not mark domain commands as pass-throughs merely to suppress findings.

## What the check establishes

The owning implementation is `_is_pass_through` in
`scitex_dev/_cli/audit/_summary/_audit.py`. `_walk` in the sibling `_walker.py`
checks universal flags (§2) before applying the declaration. Non-root declared
pass-throughs then return from that walker before its naming/help checks and
child traversal; root declarations skip the root version/spec-help checks.
A declaration therefore narrows inspection; it does not prove the callback
preserves arguments, exit status or side effects, or qualifies downstream tools.

The existing controls in
`tests/scitex_dev/_cli/audit/_summary/test__audit.py` cover
`TestIsPassThrough` (both flags, the private attribute, absent and partial
settings) and `TestPassThroughBypassesRule1`. Keep separate behavioral evidence
for the owning wrapper's actual forwarding and separator contract.
