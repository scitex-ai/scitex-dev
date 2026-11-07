---
description: |
  [TOPIC] Retired Dev skill-trigger harness
  [DETAILS] The former scitex_dev._agentic_testing skill factories and agentic-test image are not current Dev interfaces. Discover the installed newb leaf's own evaluation instructions and keep explicit skill reads, answer correctness and agent-selection evidence distinct.
tags: [scitex-dev-agentic-test-skills]
---

# Skill-trigger evaluation: retired Dev interface

Dev does not currently provide `scitex_dev._agentic_testing` or
`make_skill_trigger_tests`. The old container image, credential-mount recipes and
provider-specific harness instructions were retired; they are not installation
or test instructions for the current package.

The standalone `newb` package owns its evaluation behavior. If installed, inspect
its actual help and registered skills rather than copying an old Dev factory:

```bash
scitex newb --help
scitex dev skills list --package newb --json
```

Unavailable commands or an empty provider result do not establish evaluation
coverage. Do not install or run a paid-provider evaluation merely to inspect its
instructions.

Keep these observations separate when evaluating skill discovery:

- What metadata the agent was actually shown, with owner and version.
- Whether the skill body was read through an observed mechanism.
- Whether the answer or resulting state satisfied the task.

Correct answer text alone does not prove the agent loaded a skill: it may have
obtained the same information elsewhere. Context metadata accounting is covered
by [42_context-discovery.md](42_context-discovery.md); deterministic MCP handler
checks are covered by [32_agentic-test-mcp.md](32_agentic-test-mcp.md).
