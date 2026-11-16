"""MCP tools for the linter engine owned by scitex-dev."""


def register_all_tools(mcp) -> None:
    """Register all MCP tools with the server."""
    from .lint import register_lint_tools

    register_lint_tools(mcp)
    _register_skills_tools(mcp)


def _register_skills_tools(mcp) -> None:
    """Register skills MCP tools."""

    @mcp.tool()
    def linter_skills_list() -> dict:
        """List scitex-dev's bundled linter skill pages and their installed owner metadata."""
        try:
            from scitex_dev.ecosystem import list_skills

            result = list_skills(package="scitex-dev-linter")
            return {"success": True, "skills": result.get("scitex-dev-linter", [])}
        except ImportError:
            return {"success": False, "error": "scitex-dev not installed"}

    @mcp.tool()
    def linter_skills_get(name: str = None) -> dict:
        """Read a bundled scitex-dev linter skill by name; omit name for its overview."""
        try:
            from scitex_dev.ecosystem import get_skill

            content = get_skill(
                package="scitex-dev-linter", name=name, owner="scitex-dev"
            )
            if content:
                return {"success": True, "name": name, "content": content}
            return {"success": False, "error": f"Skill '{name}' not found"}
        except ImportError:
            return {"success": False, "error": "scitex-dev not installed"}
