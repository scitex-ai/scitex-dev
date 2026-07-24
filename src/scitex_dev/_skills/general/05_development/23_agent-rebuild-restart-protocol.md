---
description: |
  [TOPIC] Agent rebuild/restart protocol for stale container/overlay layers
  [DETAILS] When infra packages (`scitex-agent-container`, `scitex-todo`,
  `claude-code-telegrammer`) change, the container/overlay layers (5, 6) are
  stale until a rebuild+restart: release the infra packages first, rebuild the
  base image once, rolling-restart agents at a coordinated low-activity window
  (never mid-task/session), and prefer an interim env shim over a disruptive
  emergency restart. Batch it — don't restart per-merge. Companion to
  13_version-drift-management.md.
tags: [scitex-general-development-version-drift]
---

# Agent rebuild/restart protocol

## 6. Agent rebuild/restart protocol

When **infra packages** change (`scitex-agent-container`,
`scitex-todo`, `claude-code-telegrammer` — the ones every agent's
runtime depends on), the container/overlay layers (5, 6) are stale until
a rebuild+restart. Protocol:

1. **Release the infra packages first** (§3 through step 3) so the image
   build pulls a stable published version, not a moving editable.
2. **Rebuild the base image once** so its baked venv has the new
   versions.
3. **Rolling-restart agents onto the new image** — one at a time, at a
   coordinated low-activity window. A restart drops the agent's live
   session, so:
   - never restart an agent mid-task or mid-operator-session;
   - let each agent reach a natural break and self-restart (or ping
     `scitex-agent-container` for `sac agents restart <name> -y`);
   - a plain restart only picks up the change if the image/deploy was
     rebuilt first — otherwise it re-materializes the same stale state.
4. **Interim workaround** beats a disruptive emergency restart: if a
   change only needs a config/env fix, a targeted `env -u VAR` /
   `unset VAR` shim (cf. the `SCITEX_TODO_AGENT` legacy-var episode)
   keeps the agent working until its natural restart window.

**Answer to "when do I rebuild/restart all agents?"** — batch it:
release the changed infra packages, rebuild the image once, then
rolling-restart at the next quiet window. Don't restart per-merge; the
interim shims cover the gap, and a coordinated wave avoids N disruptive
session-drops.
