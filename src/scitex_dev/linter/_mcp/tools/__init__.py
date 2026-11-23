#!/usr/bin/env python3
"""MCP tool registration for scitex-linter."""


def register_all_tools(mcp) -> None:
    """Register all MCP tools with the server."""
    from .lint import register_lint_tools

    register_lint_tools(mcp)
    _register_skills_tools(mcp)


def _register_skills_tools(mcp) -> None:
    """Register tools backed by the installed linter skill namespace."""

    @mcp.tool()
    def linter_skills_list() -> dict:
        """List enabled installed linter guides from their scitex-dev owner."""
        from scitex_dev._ecosystem._skills.skills import list_skills

        result = list_skills(package="scitex-dev-linter")
        return {"success": True, "skills": result.get("scitex-dev-linter", [])}

    @mcp.tool()
    def linter_skills_get(name: str = None) -> dict:
        """Read an enabled installed linter guide, or its index when omitted."""
        from scitex_dev._ecosystem._skills.skills import get_skill

        content = get_skill(package="scitex-dev-linter", name=name, owner="scitex-dev")
        if content:
            return {"success": True, "name": name, "content": content}
        return {"success": False, "error": f"Skill '{name}' not found"}
