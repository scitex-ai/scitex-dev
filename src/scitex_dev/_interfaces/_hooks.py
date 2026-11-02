"""Dev declares its shared interface checks as a leaf hook provider."""

from __future__ import annotations


def interface_hooks():
    from scitex_dev.hooks import HookRule

    return [
        HookRule(
            id=f"dev.five-interface-{suffix}",
            rule="Require real Python, CLI, MCP, Web API and skills source bindings, or explicit narrow reasoned exceptions.",
            reason="An absent interface was silently skipped by its quality auditor, leaving installed capabilities undiscoverable and inconsistent.",
            event=event,
            severity="deny",
            matches=tools,
            provider="scitex-dev",
            owner_module="scitex_dev",
            check="scitex_dev._interfaces._hook:check_payload",
            doctrine="_skills/general/03_interface/00_overview.md",
        )
        for suffix, event, tools in (
            ("commit", "pre-tool-use", ("Bash", "terminal")),
            (
                "changed-source",
                "post-tool-use",
                (
                    "Write",
                    "Edit",
                    "MultiEdit",
                    "write_file",
                    "patch",
                    "apply_patch",
                    "Bash",
                    "terminal",
                ),
            ),
        )
    ]
