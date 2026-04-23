---
name: agentic-test-overview
description: Overview of SciTeX agentic testing — four layers across skills and MCP, shared newbie-docker substrate, claude -p plan-quota execution. Use when planning or explaining the agentic test harness.
---

# 16_agentic-test-overview

Umbrella for SciTeX's **agentic testing** family — evaluations that run
inside a clean Claude Code instance to measure whether skills and MCP
servers behave as intended end-to-end.

See the split leaves:

- [17_agentic-test-skills.md](17_agentic-test-skills.md) — skill
  trigger-rate (Layer 2): does Claude view the expected `SKILL.md`?
- [18_agentic-test-mcp.md](18_agentic-test-mcp.md) — MCP evaluation
  (Layer 2+3): does Claude call the expected tool(s) with the right
  arguments and follow through?

## Why agentic tests exist

Structural tests (see `_skills_quality_pytest`, enforced per package via
`tests/test_skills_quality.py`) prove a skill *looks* right — prefix
numbering, index consistency, no monoliths. Agentic tests prove it
*fires* and *helps* — a perfect-looking skill that Claude never consults
is dead weight.

## The four layers

Adapted from Anthropic's `skill-creator` methodology:

| Layer | Question | Measured by |
|-------|----------|-------------|
| 1. Structure  | Does the skill look right?                | `_skills_quality_pytest` (§1–§4 checklist) |
| 2. Trigger    | Does Claude view the skill for the query? | `_agentic_testing_pytest` — tool-use log |
| 3. Compliance | Does the output follow the skill?         | LLM-as-judge over output + skill body |
| 4. Outcome    | Does the end-user goal succeed?           | E2E (file produced, MCP tool succeeded) |

This leaf is the entry point. The two siblings (17, 18) specialise
Layers 2-4 for skills and MCP respectively.

## Shared substrate — newbie-docker

All agentic tests (skill + MCP) share the same isolation primitive:

- **Clean container** — `scitex-agentic-test:latest`, built from
  `scitex-agent-container:latest`. Node + claude CLI baked in.
- **No host `~/.claude` mount** — the image's `/home/agent/.claude/` is
  its own clean slate. No host projects, no CLAUDE.md, no memory, no
  ywatanabe skills.
- **Credentials, not API key** — mount *only*
  `~/.claude/.credentials.json` (copied to a world-readable tmp first
  because container uid ≠ host uid). Claude Code runs under your Max
  plan quota → **$0 real cost** regardless of the `total_cost_usd`
  reported in the JSON envelope.
- **Skills baked at build time** — the specific test skill (e.g.
  `kv-lookup` for harness-validation, or `scitex-io/SKILL.md` for a
  real-skill eval) goes into the image via `COPY` so the container
  starts with exactly the skill set under test and nothing more.

### Minimal one-shot invocation

```bash
# 1. One-time: writable credentials copy for the mount
install -m 644 ~/.claude/.credentials.json /tmp/newbie_creds.json

# 2. Run one query
docker run --rm \
  -v /tmp/newbie_creds.json:/home/agent/.claude/.credentials.json \
  scitex-agentic-test:latest \
  -p "What is the value of banana?" \
  --output-format json --model claude-haiku-4-5 \
  --dangerously-skip-permissions
```

This is the base primitive. Layers 2-4 parse the returned JSON differently.

## Why `claude -p`, not the Anthropic API

- **Plan quota covers it**, reported `total_cost_usd` is informational.
- Same tool-use semantics as an interactive Claude Code session — skills
  are discovered the way they are in production.
- No API key plumbing, no billing surprises, no rate-limit config.
- Drawback: non-deterministic across runs (plan quota ≠ API raw) — we
  mitigate with 3 runs and a 2-of-3 threshold.

## Honest caveats

- Non-determinism → 2/3 threshold, not 3/3.
- Substantive multi-step queries are required; one-step queries rarely
  trigger a skill even with a perfect description (Claude Code auto-
  loads skill bodies and answers from them directly).
- Over-triggering is a real failure mode — every positive eval should
  have at least one adjacent negative case.
- Single-container-per-process → not yet safe for `pytest-xdist` worker
  parallelism.
- Image must be rebuilt when the baked skill body changes; tag the
  image with the date to get a reproducibility anchor for papers.

## File map

```
scitex-agent-container/containers/
├── Dockerfile                       # base image (Node + claude CLI)
└── Dockerfile.agentic-test          # test image (FROM base) + baked skills

scitex-dev/src/scitex_dev/
├── _agentic_testing.py              # HostRunner, NewbieDockerRunner
├── _agentic_testing_pytest.py       # make_skill_trigger_tests(...)
├── _agentic_testing_poc.py          # CLI: one-shot prompt
└── _skills/scitex-dev/
    ├── 16_agentic-test-overview.md  # this file
    ├── 17_agentic-test-skills.md    # skill-trigger specifics
    └── 18_agentic-test-mcp.md       # MCP-eval specifics
```
