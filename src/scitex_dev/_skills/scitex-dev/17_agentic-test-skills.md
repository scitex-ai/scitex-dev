---
name: agentic-test-skills
description: Skill trigger-rate testing — does Claude view the expected SKILL.md when asked a realistic multi-step question. Use when adding trigger tests for a package's skills.
---

# 17_agentic-test-skills

Layer 2 of agentic testing (see [16_agentic-test-overview.md]). Given a
clean Claude Code instance and exactly one scoped skill catalog, measure
whether a realistic user query causes Claude to view the expected
`SKILL.md`.

## What gets measured

Parse the `claude -p --output-format json` envelope; walk recursively
for every `tool_use` block where `name ∈ {Read, view}`; collect the
`path` / `file_path` argument. A case **passes** if any collected path
substring-matches the eval's `expected_skill`. Negative cases pass when
**no** `SKILL.md` is viewed.

2-of-3 threshold across 3 runs per case — flap tolerance without
masking real regressions.

## Generic image (built once, used for all skill evals)

```bash
cd /home/ywatanabe/proj/scitex-agent-container/containers
docker build -f Dockerfile.agentic-test -t scitex-agentic-test:latest .
```

The image contains only Node + claude CLI. No baked skills, no baked
credentials. Rebuild only when the base image changes.

## Per-run staging (skills mounted at runtime)

```bash
# Writable credentials copy once per session
install -m 644 ~/.claude/.credentials.json /tmp/newbie_creds.json

# Per-eval staging dir — just the skills under test
run_id=evalrun_$(date +%s)
mkdir -p /tmp/$run_id/skills/<pkg>
cp -rf path/to/<pkg>/SKILL.md /tmp/$run_id/skills/<pkg>/SKILL.md

# Fire the query
docker run --rm \
  -v /tmp/$run_id/skills:/home/agent/.claude/skills:ro \
  -v /tmp/newbie_creds.json:/home/agent/.claude/.credentials.json \
  scitex-agentic-test:latest \
  -p "<query>" --output-format json --model claude-haiku-4-5 \
  --dangerously-skip-permissions
```

Skill edit → rerun immediately; no rebuild. To test a different skill
scope, change the staging directory contents, not the image.

Reproducibility anchor for papers: record the generic image tag
(`scitex-agentic-test:<date>`) + the staged skill fileset (content-
addressable hash of `/tmp/<run_id>/skills/`). Both pinned together
describe the exact environment measured.

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
