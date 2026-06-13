"""Configuration system for scitex-linter."""

from __future__ import annotations

__all__ = ["LinterConfig", "load_config"]

import fnmatch
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None  # type: ignore


@dataclass
class LinterConfig:
    """Configuration for scitex-linter behavior."""

    severity: str = "info"
    exclude_dirs: list[str] = field(
        default_factory=lambda: [
            "__pycache__",
            ".git",
            "node_modules",
            ".tox",
            "venv",
            ".venv",
        ]
    )
    library_patterns: list[str] = field(
        default_factory=lambda: [
            "__*__.py",
            "test_*.py",
            "conftest.py",
            "setup.py",
            "manage.py",
            "settings.py",
            "settings_*.py",
            "urls.py",
            "apps.py",
            "admin.py",
            "models.py",
            "views.py",
            "wsgi.py",
            "asgi.py",
            "conf.py",
        ]
    )
    library_dirs: list[str] = field(
        default_factory=lambda: ["src", "tests", "apps", "config", "docs"]
    )
    script_dirs: list[str] = field(default_factory=lambda: ["scripts"])
    disable: list[str] = field(default_factory=list)
    enable: list[str] = field(default_factory=list)
    per_rule_severity: dict[str, str] = field(default_factory=dict)
    category_severity_override: dict[str, str] = field(default_factory=dict)
    """Category → severity override map, applied after ``per_rule_severity``.

    Populated by :func:`load_config` from the project's
    ``.scitex/dev/config.yaml`` ``project-type`` declaration — research-
    typed projects flip the ``io`` and ``path`` categories from
    ``warning`` to ``error`` so a raw ``pd.read_parquet`` / bare
    ``open()`` blocks rather than just warns. Per the 2026-06-12
    operator directive 12826: research-category scripts must not bypass
    clew/io provenance silently. See Pillar 3 (#TBD).

    Per-rule overrides in ``per_rule_severity`` still win — set a specific
    rule's severity in pyproject.toml ``[tool.scitex-linter.per-rule-
    severity]`` to opt out of the category-wide flip for that one rule.
    """
    required_injected: list[str] = field(
        default_factory=lambda: ["CONFIG", "plt", "COLORS", "rngg", "logger"]
    )


# =============================================================================
# Configuration Loading
# =============================================================================


def load_config(start_path: str | None = None) -> LinterConfig:
    """
    Load configuration from defaults, pyproject.toml, and environment variables.

    Priority: env vars > pyproject.toml > defaults

    Args:
        start_path: File or directory to start pyproject.toml search from.
            If a file path, searches from its parent directory.
            Defaults to cwd.

    Returns:
        Merged configuration
    """
    # Start with defaults
    config_dict = {}

    # Load from pyproject.toml — resolve file paths to their directory
    if start_path:
        start_dir = Path(start_path).resolve()
        if start_dir.is_file():
            start_dir = start_dir.parent
    else:
        start_dir = Path.cwd()
    pyproject_config = _load_pyproject(start_dir)
    config_dict.update(pyproject_config)

    # Load from environment variables (highest priority)
    env_config = _load_env()
    config_dict.update(env_config)

    # Pillar 3 (#TBD, 2026-06-12 operator directive 12826): when the
    # project is research-typed (declared in .scitex/dev/config.yaml as
    # `project-type: research`), flip the io / path category severities
    # from "warning" to "error" so a raw `pd.read_parquet` / bare
    # `open()` BLOCKS the script-edit hook rather than just warning the
    # agent. Per-rule overrides in `per_rule_severity` still win — the
    # category map is the floor, not the ceiling. Walk-up + YAML parse
    # lives in `_project_type.py` (src↔tests 1:1 mirror invariant).
    from ._project_type import detect_scitex_dev_project_types

    if "research" in detect_scitex_dev_project_types(start_dir):
        existing = config_dict.get("category_severity_override", {}) or {}
        merged = {"io": "error", "path": "error", **existing}
        config_dict["category_severity_override"] = merged

    # Build LinterConfig with merged values
    return LinterConfig(**config_dict)


def _load_pyproject(start_dir: Path) -> dict:
    """
    Walk up directories to find pyproject.toml with [tool.scitex-linter].

    Args:
        start_dir: Starting directory for search

    Returns:
        Configuration dict from [tool.scitex-linter], or empty dict if not found
    """
    if tomllib is None:
        return {}

    current = start_dir
    while True:
        pyproject_path = current / "pyproject.toml"
        if pyproject_path.exists():
            try:
                with open(pyproject_path, "rb") as f:
                    data = tomllib.load(f)
                    tool_config = data.get("tool", {}).get("scitex-linter", {})
                    if tool_config:
                        # Flatten nested sections
                        config = {}
                        for key, value in tool_config.items():
                            if key == "per-rule-severity":
                                config["per_rule_severity"] = value
                            elif key == "session":
                                # Handle [tool.scitex-linter.session]
                                if "required_injected" in value:
                                    config["required_injected"] = value[
                                        "required_injected"
                                    ]
                            else:
                                # Convert kebab-case to snake_case
                                config[key.replace("-", "_")] = value
                        return config
            except Exception:
                pass

        # Move up one directory
        parent = current.parent
        if parent == current:
            # Reached filesystem root
            break
        current = parent

    return {}


_ENV_PREFIX_NEW = "SCITEX_DEV_LINTER_"
_ENV_PREFIX_OLD = "SCITEX_LINTER_"

# Per-suffix mapping: canonical (new) → list of legacy aliases. The first
# matching env var wins; any legacy hit emits a one-time DeprecationWarning.
# Add aliases here when an env var is renamed; do NOT silently drop them
# — a one-release deprecation window is the soft-migration policy.
_ENV_RENAMES: dict[str, list[str]] = {
    # Renamed for clarity — the dirs in question hold *non-script* code (no
    # @stx.session decorator / __main__ guard expected). The old name
    # "LIBRARY_DIRS" was ambiguous against EXCLUDE_DIRS.
    "NON_SCRIPT_DIRS": ["LIBRARY_DIRS"],
}

_warned_aliases: set = set()


def _read_env(suffix: str) -> str | None:
    """Read an env var, preferring the new prefix + canonical name.

    Falls back to: (1) new prefix + legacy alias, (2) old prefix + canonical
    name, (3) old prefix + legacy alias. Any legacy hit emits a one-time
    DeprecationWarning naming the canonical replacement.
    """
    aliases = [suffix] + _ENV_RENAMES.get(suffix, [])
    for prefix, prefix_label in (
        (_ENV_PREFIX_NEW, "new"),
        (_ENV_PREFIX_OLD, "old"),
    ):
        for alias in aliases:
            name = prefix + alias
            if name in os.environ:
                canonical = _ENV_PREFIX_NEW + suffix
                if name != canonical and name not in _warned_aliases:
                    import warnings

                    warnings.warn(
                        f"Env var {name!r} is deprecated; use {canonical!r}.",
                        DeprecationWarning,
                        stacklevel=4,
                    )
                    _warned_aliases.add(name)
                return os.environ[name]
    return None


def _read_env_csv(suffix: str) -> list | None:
    raw = _read_env(suffix)
    if raw is None:
        return None
    return [x.strip() for x in raw.split(",") if x.strip()]


def _load_env() -> dict:
    """Load configuration from `SCITEX_DEV_LINTER_*` environment variables.

    The legacy `SCITEX_LINTER_*` prefix is also accepted for the soft-migration
    window and emits a `DeprecationWarning`.

    Returns:
        Configuration dict with snake_case keys
    """
    config: dict = {}

    severity = _read_env("SEVERITY")
    if severity is not None:
        config["severity"] = severity

    for suffix, key in (
        ("DISABLE", "disable"),
        ("ENABLE", "enable"),
        ("EXCLUDE_DIRS", "exclude_dirs"),
        ("NON_SCRIPT_DIRS", "library_dirs"),
        ("SCRIPT_DIRS", "script_dirs"),
        ("LIBRARY_PATTERNS", "library_patterns"),
        ("REQUIRED_INJECTED", "required_injected"),
    ):
        values = _read_env_csv(suffix)
        if values is not None:
            config[key] = values

    return config


# =============================================================================
# Utility Functions
# =============================================================================


def matches_library_pattern(filename: str, config: LinterConfig) -> bool:
    """
    Check if filename matches any library pattern in config.

    Args:
        filename: Filename to check (e.g., "__init__.py", "test_foo.py")
        config: Linter configuration

    Returns:
        True if filename matches any pattern
    """
    for pattern in config.library_patterns:
        if fnmatch.fnmatch(filename, pattern):
            return True
    return False
