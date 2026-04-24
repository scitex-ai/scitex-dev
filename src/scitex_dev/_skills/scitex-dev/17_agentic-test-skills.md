---
name: agentic-test-skills
description: Skill trigger-rate testing — does Claude view the expected SKILL.md when asked a realistic multi-step question. Use when adding trigger tests for a package's skills.
---

# 17_agentic-test-skills

Layer 2 of agentic testing (see [16_agentic-test-overview.md]). Given a
clean Claude Code instance and exactly one scoped skill catalog, measure
whether a realistic user query causes Claude to view the expected
`SKILL.md`.

## What gets measured — hard vs soft trigger

Per official Claude Code docs (`Extend Claude with skills.md`, 2026-04):

> "In a regular session, skill descriptions are loaded into context so
> Claude knows what's available, but full skill content only loads
> when invoked."

Two distinct trigger signals exist:

- **Hard trigger**: a `tool_use` block with `name ∈ {Read, view}` and a
  path that substring-matches the expected `SKILL.md`. Explicit, easy
  to extract from the JSON envelope.
- **Soft trigger**: no explicit `Read`, but the skill body was
  auto-loaded from description match (standard Claude Code behavior)
  and the response contains skill-specific content. `tool_use` count
  is 0 yet the answer is still correct.

**Measuring only hard triggers underestimates true trigger rate.**
Verified empirically 2026-04-23: with a pushy "ALWAYS invoke this
skill when... Do not answer from training" description on scitex-io's
SKILL.md, Claude returned the correct API (`sio.save(df, ...,
use_caller_path=True)`) with zero `tool_use` — proof that the skill
body was consulted via auto-load.

### Recommended eval JSON additions

```json
{
  "id": "case-1",
  "query": "<substantive multi-step query>",
  "expected_skill": "scitex-io/SKILL.md",
  "answer_contains": ["use_caller_path=True", "stx.io.save"],
  "complexity": "high"
}
```

- **Hard-trigger pass** if the `Read`/`view` tool-use path matches.
- **Soft-trigger pass** if every string in `answer_contains` appears
  in `result`.
- A case passes the run if **either** trigger type passes.
- 2-of-3 threshold still applies across 3 runs per case.

Author guidance: choose `answer_contains` strings that are authored
in the skill body and unlikely to appear from model training alone.
The presence of `use_caller_path=True` in an answer about scitex-io
is a strong soft-trigger signal because the flag is SciTeX-specific.

## Generic image (built once, used for all skill evals)

```bash
cd /home/ywatanabe/proj/scitex-agent-container/containers
docker build -f Dockerfile.agentic-test -t scitex-agentic-test:latest .
```

The image contains only Node + claude CLI. No baked skills, no baked
credentials. Rebuild only when the base image changes.

## Two runtime modes (pick by purpose)

One shared credentials copy (session scope):

```bash
install -m 644 ~/.claude/.credentials.json /tmp/newbie_creds.json
```

### Mode A — dev iteration (direct source mount)

Fastest feedback loop — edit the source `SKILL.md` in the package
repo and the next `docker run` reflects it instantly. **No export, no
staging, no rebuild.**

```bash
docker run --rm \
  -v ~/proj/scitex-io/src/scitex_io/_skills/scitex-io:/home/agent/.claude/skills/scitex-io:ro \
  -v /tmp/newbie_creds.json:/home/agent/.claude/.credentials.json \
  scitex-agentic-test:latest \
  -p "<query>" --output-format json --model claude-haiku-4-5 \
  --dangerously-skip-permissions
```

For a multi-skill scope, add one `-v <repo>/.../_skills/<pkg>:/home/agent/.claude/skills/<pkg>:ro` per package. The container sees exactly those
skills and nothing else.

### Mode B — production test (pip install + export)

Exercises the **real install path** — what a fresh user gets when they
`pip install scitex-io` and the shipped skill lands in
`~/.claude/skills/scitex/<pkg>/`. Use this to catch packaging bugs
(missing `_skills/` in the wheel, export script failures, etc.).

```bash
# Inside a derived image OR a Python env
pip install scitex-io

# Export the skill into a staging dir
scitex-io skills export --dest /tmp/evalrun_io/.claude/skills --clean

# Mount the staged result
docker run --rm \
  -v /tmp/evalrun_io/.claude/skills:/home/agent/.claude/skills:ro \
  -v /tmp/newbie_creds.json:/home/agent/.claude/.credentials.json \
  scitex-agentic-test:latest \
  -p "<query>" --output-format json --model claude-haiku-4-5 \
  --dangerously-skip-permissions
```

Mode B is the **canonical CI target** — it measures what users
actually experience. Mode A is for tightening the skill's trigger
behavior before committing.

Reproducibility anchor for papers: record the generic image tag
(`scitex-agentic-test:<date>`) plus either the mode-A source commit
SHA or the mode-B exported skill hash. Both forms fully describe
the measured environment.

## MVP — Phase 1 (synthetic kv-lookup)

The harness-validation skill lives at
`scitex-agent-container/containers/skills/kv-lookup/SKILL.md`. Pushy
description enumerates trigger words (`apple, banana, cherry, date,
elderberry`). Body holds the authoritative lookup table.

Result measured 2026-04-23 — **8/8 trigger + answer OK at $0.088 over
54 s** across 4 cases × 2 runs:

| case | expected | trigger | answer |
|------|----------|---------|--------|
| banana     | kv-lookup | 2/2 | "12"   |
| cherry     | kv-lookup | 2/2 | "42"   |
| elderberry | kv-lookup | 2/2 | "256"  |
| fig (neg)  | none      | 2/2 | refused, cited kv-lookup by name |

`tool_uses: []` on some runs is expected — Claude Code auto-loads small
skill bodies from the description match; it doesn't always explicitly
`Read` the file. For compliance measurement (Layer 3) we still check
the answer content, not just the tool call.

## Drop-in pytest per package

```python
# tests/test_skill_trigger.py
from scitex_dev._agentic_testing_pytest import make_skill_trigger_tests

test_skill_trigger = make_skill_trigger_tests(
    eval_path="tests/skill_evals/<pkg>.json",
    model="claude-haiku-4-5",
    backend="docker",          # or "host" for quick dev
)
```

Marker applied automatically — run only trigger tests:

```bash
pytest -m skill_trigger
```

## Writing the eval JSON

Copy from `examples/skill_eval_example.json`:

```json
{
  "version": 1,
  "evals": [
    {"id": "substantive-pos", "query": "<multi-step query ~80-200 chars>",
     "expected_skill": "scitex-io/SKILL.md", "complexity": "high"},
    {"id": "adjacent-neg",    "query": "<query near the skill's domain but outside its remit>",
     "expected_skill": null, "complexity": "low"}
  ]
}
```

Rules:

1. **Substantive, multi-step.** Simple one-step queries Claude answers
   from training without consulting any skill.
2. **Don't name the skill in the query.** That's a trivially-passing
   test that measures description quality = 0.
3. **Pair every positive with a near-adjacent negative.** Over-trigger
   is a bug equal in weight to under-trigger.
4. **One expected skill per case.** Multi-skill disambiguation is a
   separate test shape.

## Environment variables

| Var | Meaning | Default |
|---|---|---|
| `SCITEX_DEV_AGENTIC_BACKEND`            | `host` or `docker` | `host` |
| `SCITEX_DEV_AGENTIC_DOCKER_IMAGE`       | image tag | `scitex-agent-container:latest` |
| `SCITEX_DEV_CLAUDE_ACCOUNTS`            | `:`-separated HOME dirs for host rotation | `~` |

Credentials for the docker backend are mounted, not env'd. See the
overview for the mount recipe.

## Threshold, retries, model

- **Threshold: 2 of 3** runs per case must pass.
- **Retries: none** beyond the 3 runs — we measure trigger rate, not
  retry-to-success.
- **Haiku first**; upgrade to opus only if borderline cases need model
  capacity (rare for basic skill dispatch).

## POC / one-shot probe

```bash
python -m scitex_dev._agentic_testing_poc \
  --backend docker --prompt "What is the value of banana?"
```

Prints `duration_ms`, `cost_usd`, `cache_creation_tokens`,
viewed-paths. Good for sanity-checking a new skill before writing a
full eval JSON.

## Next — from MVP to real packages

Current MVP proves the harness works end-to-end on a synthetic skill
with runtime-mounted catalog. To measure a real package:

1. Stage the package's `SKILL.md` (and any referenced leaves) under
   `tests/skill_evals/<pkg>_stage/skills/<pkg>/`.
2. Author `tests/skill_evals/<pkg>.json` with 3-5 substantive queries +
   at least one adjacent negative.
3. Drop in `tests/test_skill_trigger.py` (snippet above).
4. Run the trigger tests and establish baseline — for MCP-enabled
   packages, a derived image `scitex-agentic-test-<pkg>:latest` with
   `RUN pip install scitex-<pkg>` may be needed for the Python side
   (the skill itself still mounts at runtime). Keep the pip set tight
   — installing all of scitex takes >1 hour.
