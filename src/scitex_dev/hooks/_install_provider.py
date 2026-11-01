"""Install discovered leaf checks into native Claude or Hermes configuration."""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path

from ._discover import discover_hooks
from ._spec import hermes_event_for, resolve_asset


def install_provider(
    config_path, *, provider, harness="claude", dry_run=False, python=None
):
    """Merge one provider's bindings; preserve unrelated settings and hooks."""
    path = Path(config_path).expanduser().resolve()
    rules = [r for r in discover_hooks() if r.provider == provider]
    if not rules or any(not r.check for r in rules):
        raise ValueError(f"Provider {provider!r} must expose executable check bindings")
    if any(rule.script and resolve_asset(rule) is None for rule in rules):
        raise ValueError(f"Provider {provider!r} declares an unavailable script asset")
    command = shlex.join(
        [
            str(python or sys.executable),
            "-m",
            "scitex_dev.hooks.dispatch",
            "--provider",
            provider,
        ]
    )
    text = path.read_text() if path.exists() else ""
    if harness == "hermes":
        import hermes_yaml as yaml

        config = yaml.safe_load(text) or {}
    elif harness == "claude":
        config = json.loads(text) if text else {}
    else:
        raise ValueError("harness must be claude or hermes")
    if not isinstance(config, dict):
        raise TypeError("Native hook configuration must be a mapping")
    if config.get("disableAllHooks"):
        raise ValueError(
            "Native hooks are explicitly disabled; configuration preserved"
        )
    hooks = config.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise TypeError("Native hooks must be a mapping")
    events = sorted({r.event for r in rules})
    for event in events:
        if event not in ("pre-tool-use", "post-tool-use"):
            raise ValueError(
                f"Native provider installation does not support event {event!r}"
            )
        selected = [r for r in rules if r.event == event]
        matches = sorted({pattern for r in selected for pattern in r.matches})
        matcher = (
            "^(?:"
            + "|".join(
                re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
                for pattern in matches
            )
            + ")$"
        )
        if harness == "hermes":
            key = hermes_event_for(event)
            binding = {
                "command": command,
                "matcher": matcher,
                "timeout": 30,
            }
            if event == "pre-tool-use":
                binding["fail_closed"] = True
        else:
            key = {"pre-tool-use": "PreToolUse", "post-tool-use": "PostToolUse"}[event]
            binding = {
                "matcher": matcher,
                "hooks": [{"type": "command", "command": command, "timeout": 30}],
            }
        entries = hooks.setdefault(key, [])

        if not isinstance(entries, list) or any(
            not isinstance(entry, dict) for entry in entries
        ):
            raise ValueError(f"Hook entries for {key} must be mappings in a list")

        def owned_command(value):
            if not isinstance(value, str):
                return False
            try:
                words = shlex.split(value)
            except ValueError:
                return False
            return words[1:] == [
                "-m",
                "scitex_dev.hooks.dispatch",
                "--provider",
                provider,
            ]

        kept = []
        for entry in entries:
            if harness == "hermes":
                if not owned_command(entry.get("command")):
                    kept.append(entry)
            else:
                # A matcher block can contain hooks owned by several packages.
                foreign = [
                    hook
                    for hook in entry.get("hooks", [])
                    if not owned_command(hook.get("command"))
                ]
                if foreign:
                    kept.append(dict(entry, hooks=foreign))
        entries[:] = kept
        entries.append(binding)
    if not dry_run:
        if path.exists() and path.read_text() != text:
            raise ValueError("Hook configuration changed concurrently; retry the merge")
        path.parent.mkdir(parents=True, exist_ok=True)
        if harness == "hermes":
            # Runtime-owned config writer when available; no HOME substitution.
            from hermes_cli.config import atomic_config_write

            atomic_config_write(path, config)
        else:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=path.parent, delete=False
            ) as stream:
                json.dump(config, stream, indent=2)
                stream.write("\n")
                temp = Path(stream.name)
            temp.chmod(0o600)
            os.replace(temp, path)
    return {
        "provider": provider,
        "harness": harness,
        "config": str(path),
        "events": events,
        "dry_run": dry_run,
        "runtime_verified": False,
        "blocking_events": [
            event for event in events if harness == "claude" or event == "pre-tool-use"
        ],
        "observer_events": [
            event
            for event in events
            if harness == "hermes" and event == "post-tool-use"
        ],
        "activation": (
            "Native consent and startup/plugin reload required; post_tool_call cannot block."
            if harness == "hermes"
            else "Native client must load the settings; verify an actual tool refusal."
        ),
    }
