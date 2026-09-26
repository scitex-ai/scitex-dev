---
description: |
  [TOPIC] Choosing the Interface Surface
  [DETAILS] Which surface should carry a capability — MCP tool, CLI tool, Skill, Hook, or harness-neutral startup policy — decided by what must be true at RUNTIME rather than what is easiest to write. Covers the one-line guarantee and hard limit of each, why MCP and CLI differ only in who pays for discoverability, why a skill is advice while a hook is enforcement only in harnesses that invoke it, and why always-loaded startup policy is the most expensive real estate. Includes the decision checklist and the startup-policy SSOT/projection boundary for CLAUDE.md, AGENTS.md, and Hermes. Use when adding a capability and unsure where it belongs, when prose keeps being violated, when startup instructions are growing, or when reviewing whether an existing surface choice was right.
tags: [scitex-general-interface-surface-choice]
---

# MCP vs CLI tools vs skills vs hooks vs startup policy

Five surfaces can carry a capability. They fail in different ways, and the
WHY behind each choice is the point: pick by **what must be true at runtime**,
not by what is easiest to write.

## The one-line WHY for each

| Surface | What it guarantees | What it can NEVER do | Context cost |
|---|---|---|---|
| **MCP tool** | Discoverable action: the schema is pushed into context, so the model can call it *without knowing it exists beforehand* | Judgment; enforcement; working when the server is down | Per-tool tokens, every session |
| **CLI tool** | Deterministic, versioned, testable action; humans and agents share the exact same entry point | Being discovered on its own — the model must be TOLD it exists | Zero until invoked |
| **Skill** | Knowledge on demand: WHEN to act, HOW to judge, which tools to reach for | Detecting events; guaranteeing anything (the model may never load it) | Loaded only when triggered |
| **Hook** | Deterministic enforcement/detection at the boundaries where the active harness actually invokes it | Judgment, nuance, multi-step reasoning; enforcement in a harness that does not support or install the hook | Zero model tokens when external |
| **Startup-policy projection** | Always-loaded instructions when the active harness finds and loads its projection | Enforcement; portability when hand-edited separately per harness | Highest: always in context |

Rule of thumb: **mechanism → code (CLI/MCP/hook); judgment → skill;
universal instruction → startup-policy source.** If a behavior must *always*
happen (or never happen), prose cannot guarantee it — use an enforcement
boundary supported by every in-scope runtime. If it requires weighing context,
code alone cannot decide it — that is skill territory.

## MCP vs CLI — same role, opposite discovery

Both DO things against real systems. The difference is who pays for
discoverability:

- **MCP** pushes its tool schemas into the model's context: instant
  discovery, but every tool costs tokens in every session, and a dead
  server silently removes the capability.
- **CLI** costs nothing until used and stays testable/versionable in CI,
  but the model must *actively* learn it exists and what its flags are —
  from `--help`, from a skill, or from startup policy. A CLI nobody points to is
  functionally invisible.

So yes: **CLI tools are guided from skills.** The skill (or startup-policy line)
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

A skill that says "never edit on develop" is advice. A hook that rejects the
edit is a guarantee only inside runtimes that are proven to invoke that hook.
Use hooks for:

- **Enforcement**: house rules that must hold under pressure (branch
  protection, format gates). The model cannot negotiate with an exit code,
  but a harness can bypass an uninstalled hook.
- **Detection/injection**: a harness event API can notice an event and inject
  context when that API is enabled. Event names and guarantees are
  harness-specific; they do not belong in the shared policy domain.

Keep hooks narrow and dumb: one rule, one educational error message
pointing at the sanctioned alternative. Judgment about *why* the rule
exists belongs in a skill the error message can reference; the pairing
(hook enforces + skill explains) beats either alone.

## Startup policy — one authority, thin harness projections

Keep universal instructions in one harness-neutral startup-policy source of
truth. Generate thin `CLAUDE.md`, `AGENTS.md`, and Hermes projections from it;
do not maintain three independent policies. Each adapter may translate only
the minimum discovery/bootstrap syntax required by its harness. It must not
invent domain rules.

Treat projections as generated artifacts. Carry the authoritative source hash
and validate it so stale, locally edited, or missing projections fail loud.
The existence of this skill does **not** mean a repository already has that
generator or validator: verify the runtime command and its tests before
claiming enforcement. Until then, these files are instructions, not guarantees.

Always-loaded instructions are the most expensive real estate. Reserve them
for identity, safety posture, and workflow rules that apply to every task.
Move topical judgment into triggered skills. Move enforceable rules into code
only after every in-scope harness has a tested boundary that invokes it.

## Decision checklist

1. Must it ALWAYS/NEVER happen? → **hook** (plus a skill explaining why).
2. Is it an action against a live system? → **CLI** if deterministic and
   human-shared, **MCP** if it must be discoverable or session-bound;
   ideally CLI core + thin MCP mirror.
3. Is it workflow, judgment, or when-to-use knowledge? → **skill** (which
   also advertises the CLIs).
4. Does every task need it, on every prompt? → **startup-policy source**, in
   as few lines as possible; generate the harness projections.
5. Still unsure? Build the mechanism as a CLI (testable), document the
   judgment as a skill, and only escalate to a hook/startup-policy rule when a
   real violation shows the need.

## Related skills

Use the active harness's MCP and skill-authoring guidance when available. Those
helpers are tooling, not SciTeX authorities, and their names and installation
paths are harness-specific. The package-local documents below define the
portable SciTeX contract.

Within this package, the neighbouring interface docs are `02_cli/` (noun-verb command structure), `03_mcp/` (server registration), and `04_skills/` (frontmatter, indexing, export).

## MCP vs Skills (original comparison)

| MCP (Connectivity)                                  | Skills (Knowledge)                                  |
| ---------------------------------------------------- | ---------------------------------------------------- |
| Connects an agent to your service                    | Teaches an agent how to use your service effectively |
| Provides real-time data access and tool invocation   | Captures workflows and best practices                |
| What Claude can do                                   | How Claude should do it                              |

## Authoring a skill

For how to structure and write a skill (file layout, YAML frontmatter,
description patterns, templates), use this package's `04_skills/` section and,
when useful, the active harness's authoring helper. This document is only about
choosing the surface; keep authoring detail on demand.
