---
description: |
  [TOPIC] Native hook enforcement
  [DETAILS] Verify package-owned agent bindings, explicit opt-outs, native activation, and Hermes blocking limits.
tags: [scitex-dev-native-hook-enforcement]
---


## Verify native provider enforcement

The canonical bridge shipped in Dev 0.62.6. Example:

```bash
scitex-dev hooks install --provider scitex-sdk --config .claude/settings.json --harness claude --dry-run
```

Remove `--dry-run` to merge the binding while preserving unrelated settings,
existing hooks, and configuration symlinks. Install only providers you intend
to activate; removing their native binding is the provider opt-out. A native
`disableAllHooks` opt-out is preserved. Script assets, when declared, must
exist, and checks must implement the native payload-to-violation-list contract.

Installation reports configuration, not active interception. Verify an actual
prohibited native tool call before claiming coverage. Reinstalling SDK source
without refreshing installed entry-point metadata cannot advertise new rules.
For Hermes, existing native consent and startup/plugin reload are required;
the installer does not manufacture allowlist approvals. `pre_tool_call` can
veto; `post_tool_call` is an observer and cannot block completed filesystem
changes. Agent-independent project auditing/CI/pre-push gates remain necessary.
