---
description: |
  [TOPIC] Skill explanations and evidence
  [DETAILS] The current skills explain-self command resolves an authored SciTeX skills directory and delegates evaluation to installed newb. Inspect help without running an agent; distinguish generated editorial drafts, observed skill reads and source-backed behavioral verification.
tags: [scitex-general-development-skills-self-explain]
---

# Skill explanations and evidence

A fresh agent's explanation can reveal unclear skill documentation. It is
editorial evidence, not proof that the package works, that the agent read a
particular skill, or that generated README claims match the implementation.
Leaf skills remain owned documentation and must be checked against source and
installed behavior.

## Current command

Inspect the installed interface without starting an evaluation:

```bash
scitex dev skills explain-self --help
scitex dev skills list --package scitex-dev --json
```

Standalone bootstrap is `scitex-dev dev skills explain-self --help`. The hidden
`self-explain` spelling is a compatibility alias. The current command syntax is
shown here as a reference, not an instruction to run a provider:

```text
explain-self DISTRIBUTION [--model MODEL] [--runs N] [--format json|markdown]
```

An evaluation can start an agent/container and consume provider quota. Inspect
the installed `newb` implementation, runtime requirements, credentials, mounts,
model route and permissions before an authorized run. Help inspection and skill
inventory do not establish that those requirements are satisfied. Do not run a
paid evaluation merely to check these instructions.

## Ownership and source resolution

The CLI is registered in `_cli/skills/_manage/_explain_self_cmd.py`.
`_cli/skills/_self_explain.py` resolves the distribution through the ecosystem
registry and local checkout lookup. Its expected directory is:

```text
<local-checkout>/src/<import-name>/_skills/<distribution>/
```

Unknown distributions, absent local checkouts and missing directories are
reported as errors. This resolver is distinct from installed skill discovery and
from an exported agent-readable store; installing skill files alone does not
create the required authored checkout.

Dev lazily imports the declared `newb` dependency and selects its `test` callable
when present, otherwise `run`. For example, the normally installed `newb`
0.26.7 exposes `run`, not `test` or `self_explain`; do not infer a public upstream
function from the Dev wrapper's name. The retired
`scitex_dev._agentic_testing.NewbieDockerRunner` is not this implementation.

## Output and validation limits

The CLI forwards the model and run count, then emits JSON or delegates Markdown
rendering to `newb.render_markdown`. The result schema, prompts, runtime behavior
and aggregation semantics belong to the installed `newb` version. Do not promise
a median selection, a fixed number of prompts, a fixed cost, credential isolation
or a cache based on the earlier design sketch.

Review generated explanations as drafts. Verify installation instructions,
Python imports, CLI paths, results and side effects through the actual supported
interfaces before using them in README or documentation. Correct answer text
alone does not show which skills or other context the agent loaded.

Source-wiring tests live in `_cli/skills/test__self_explain.py` and
`_cli/skills/_manage/test__explain_self_cmd.py` under `tests/scitex_dev/`.
Controls using an injected runner qualify their stated local wrapper behavior;
they do not establish provider access or an actual agent's skill selection.
See [31_agentic-test-skills.md](../../scitex-dev/31_agentic-test-skills.md) for the
retired harness boundary and [22_documentation-drift.md](22_documentation-drift.md)
for broader documentation acceptance.
