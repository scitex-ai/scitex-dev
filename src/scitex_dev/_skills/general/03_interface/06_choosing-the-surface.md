---
description: |
  [TOPIC] Choosing the Interface Surface
  [DETAILS] Which of the five surfaces should carry a capability — MCP tool, CLI tool, Skill, Hook, or CLAUDE.md — decided by what must be true at RUNTIME rather than what is easiest to write. Covers the one-line guarantee and hard limit of each, why MCP and CLI differ only in who pays for discoverability, why a skill is advice while a hook is a guarantee, and why CLAUDE.md is the most expensive real estate. Includes the decision checklist. Use when adding a capability and unsure where it belongs, when a prose rule keeps being violated (promote it to a hook), when CLAUDE.md is growing (demote topical content to a skill), or when reviewing whether an existing surface choice was right.
tags: [scitex-general-interface-surface-choice]
---

# MCP vs CLI Tools vs Skills vs Hooks vs CLAUDE.md — choosing the surface

Five surfaces can carry a capability. They fail in different ways, and the
WHY behind each choice is the point: pick by **what must be true at runtime**,
not by what is easiest to write.

## The one-line WHY for each

| Surface | What it guarantees | What it can NEVER do | Context cost |
|---|---|---|---|
| **MCP tool** | Discoverable action: the schema is pushed into context, so the model can call it *without knowing it exists beforehand* | Judgment; enforcement; working when the server is down | Per-tool tokens, every session |
| **CLI tool** | Deterministic, versioned, testable action; humans and agents share the exact same entry point | Being discovered on its own — the model must be TOLD it exists | Zero until invoked |
| **Skill** | Knowledge on demand: WHEN to act, HOW to judge, which tools to reach for | Detecting events; guaranteeing anything (the model may never load it) | Loaded only when triggered |
| **Hook** | Deterministic enforcement/detection at tool-call boundaries — runs even when the model forgets, disagrees, or was never told | Judgment, nuance, multi-step reasoning | Zero (runs outside the model) |
| **CLAUDE.md** | Presence in EVERY prompt, before any tool call or skill load | Scaling — every line taxes every request forever | Highest: always in context |

Rule of thumb: **mechanism → code (CLI/MCP/hook); judgment → skill;
invariant → CLAUDE.md.** If a behavior must *always* happen (or never
happen), prose cannot guarantee it — that is hook territory. If it requires
weighing context, code cannot decide it — that is skill territory.

## MCP vs CLI — same role, opposite discovery

Both DO things against real systems. The difference is who pays for
discoverability:

- **MCP** pushes its tool schemas into the model's context: instant
  discovery, but every tool costs tokens in every session, and a dead
  server silently removes the capability.
- **CLI** costs nothing until used and stays testable/versionable in CI,
  but the model must *actively* learn it exists and what its flags are —
  from `--help`, from a skill, or from CLAUDE.md. A CLI nobody points to is
  functionally invisible.

So yes: **CLI tools are guided from skills.** The skill (or CLAUDE.md line)
is the discovery rail; the CLI is the mechanism. A well-built capability is
often a pair: `scitex-dev rename-symbols` (CLI, deterministic) + a skill
leaf saying *when* bulk-rename is the right move and *why* sed/awk are
banned.

Prefer **CLI** when the operation is deterministic, scriptable, shared with
humans, or belongs in CI. Prefer **MCP** when the model should discover the
capability unprompted, when calls need long-lived connections/sessions, or
when the consumer is only ever an agent. Mirroring a CLI as thin MCP tools
(same verbs, same nouns) gives both — discovery for agents, determinism for
humans — at the cost of maintaining the mirror.

## Hooks — when prose is not enough

A skill that says "never edit on develop" is advice; a PreToolUse hook that
rejects the edit is a guarantee. Use hooks for:

- **Enforcement**: house rules that must hold under pressure (branch
  protection, forced backgrounding, format gates). The model cannot
  negotiate with an exit code.
- **Detection/injection**: hooks are the only surface that can *notice an
  event* and push awareness into the conversation (e.g. a UserPromptSubmit
  hook scanning state and printing one context line).

Keep hooks narrow and dumb: one rule, one educational error message
pointing at the sanctioned alternative. Judgment about *why* the rule
exists belongs in a skill the error message can reference; the pairing
(hook enforces + skill explains) beats either alone.

## CLAUDE.md — the most expensive real estate

CLAUDE.md is in every prompt automatically; everything else is consumed
contextually. That makes it the only place for **invariants that apply
regardless of topic** (identity, safety posture, non-negotiable workflow
rules) — and the wrong place for anything topical, long, or rarely needed.
Every topical paragraph moved from CLAUDE.md into a triggered skill is a
permanent tax cut on every future request. If a rule is enforceable, demote
it further: hook it, then let CLAUDE.md not mention it at all.

## Decision checklist

1. Must it ALWAYS/NEVER happen? → **hook** (plus a skill explaining why).
2. Is it an action against a live system? → **CLI** if deterministic and
   human-shared, **MCP** if it must be discoverable or session-bound;
   ideally CLI core + thin MCP mirror.
3. Is it workflow, judgment, or when-to-use knowledge? → **skill** (which
   also advertises the CLIs).
4. Does every task need it, on every prompt? → **CLAUDE.md**, in as few
   lines as possible.
5. Still unsure? Build the mechanism as a CLI (testable), document the
   judgment as a skill, and only escalate to hook/CLAUDE.md when a real
   violation shows prose was not enough.

## Related Skills

These two live in the Claude Code skills directory (`~/.claude/skills/`), not in this package — invoke them by name rather than by path, since this file ships inside `scitex-dev` and installs wherever the package does:

- **`mcp-builder`** — building a new MCP server (TypeScript or Python). Reach for it when the need is NEW connectivity to a service, not knowledge about an existing one.
- **`skill-creator`** — drafting, testing and iterating a skill, including its eval tooling and description optimisation. Reach for it when capturing a workflow or judgment, per the template and description guidance below.

Within this package, the neighbouring interface docs are `02_cli/` (noun-verb command structure), `03_mcp/` (server registration), and `04_skills/` (frontmatter, indexing, export).

## MCP vs Skills (original comparison)

| MCP (Connectivity)                                  | Skills (Knowledge)                                  |
| ---------------------------------------------------- | ---------------------------------------------------- |
| Connects Claude to your service                      | Teaches Claude how to use your service effectively   |
| Provides real-time data access and tool invocation   | Captures workflows and best practices                |
| What Claude can do                                   | How Claude should do it                              |

## Good Use Case Definition

```
Use Case: Project Sprint Planning
Trigger: User says "help me plan this sprint" or "create sprint tasks"
Steps:
1. Fetch current project status from Linear (via MCP)
2. Analyze team velocity and capacity
3. Suggest task prioritization
4. Create tasks in Linear with proper labels and estimates
Result: Fully planned sprint with tasks created
```

## Technical Requirements

### File Structure

```
your-skill-name/
├── SKILL.md               # Required - main skill file
├── scripts/                # Optional - executable code
│   ├── process_data.py    # Example
│   └── validate.sh        # Example
├── references/             # Optional - documentation
│   ├── api-guide.md        # Example
│   └── examples/           # Example
└── assets/                 # Optional - templates, etc.
    └── report-template.md  # Example
```

### YAML Frontmatter

```yaml
---
name: your-skill-name
description: What it does. Use when user asks to [specific phrases].
---
```

## Writing Effective Skills

Structure formula: **[What it does] + [When to use it] + [Key capabilities]**

### Good Description Examples

```yaml
# Good — specific and actionable
description: Analyzes Figma design files and generates developer handoff documentation. Use when user uploads .fig files, asks for "design specs", "component documentation", or "design-to-code handoff".
```

```yaml
# Good — includes trigger phrases
description: Manages Linear project workflows including sprint planning, task creation, and status tracking. Use when user mentions "sprint", "Linear tasks", "project planning", or asks to "create tickets".
```

```yaml
# Good — clear value proposition
description: End-to-end customer onboarding workflow for PayFlow. Handles account creation, payment setup, and subscription management. Use when user says "onboard new customer", "set up subscription", or "create PayFlow account".
```

### Bad Description Examples

```yaml
# Too vague
description: Helps with projects.
```

```yaml
# Missing triggers
description: Creates sophisticated multi-page documentation systems.
```

```yaml
# Too technical, no user triggers
description: Implements the Project entity model with hierarchical relationships.
```

### Recommended Template

Adapt this template for your skill. Replace bracketed sections with your specific content.

````markdown
---
name: your-skill
description: [...]
---
# Your Skill Name

## Instructions

### Step 1: [First Major Step]
Clear explanation of what happens.

Example:
```bash
python scripts/fetch_data.py --project-id PROJECT_ID
```
Expected output: [describe what success looks like]
````

**Include error handling** — e.g. a section like:

````markdown
## Common Issues

### MCP Connection Failed
If you see "Connection refused":
1. Verify MCP server is running: Check Settings > Extensions
2. Confirm API key is valid
3. Try reconnecting: Settings > Extensions > [Your Service] > Reconnect
````

**Reference bundled resources clearly** — before writing queries, consult `references/api-patterns.md` for:
- Rate limiting guidance
- Pagination patterns
- Error codes and handling

**Use progressive disclosure** — keep SKILL.md focused on core instructions. Move detailed documentation to `references/` and link to it. (See Core Design Principles for how the three-level system works.)

### References

Claude Code skills, invoked by name (not shipped with this package):

- `mcp-builder`
- `skill-creator`

Both live under the Claude Code skills directory on a configured machine. Referenced by name deliberately — an absolute path would be wrong for anyone who installs `scitex-dev` from PyPI, and a stale path is worse than none.
