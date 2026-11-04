"""Shared YAML reader; strict exposure reads do not change legacy parsing."""

from pathlib import Path
from typing import Any


def validate_packages(data: dict[str, Any]) -> None:
    """Refuse malformed package selection in strict exposure snapshots only."""
    from .names import normalize_distribution_name

    if "packages" not in data:
        return
    packages = data["packages"]
    if not isinstance(packages, list):
        raise TypeError("exposure config packages must be a list")
    for package in packages:
        if not isinstance(package, dict):
            raise TypeError("exposure config package entries must be objects")
        name = package.get("name")
        if not isinstance(name, str):
            raise TypeError("exposure config package name must be a string")
        normalize_distribution_name(name)


def load_yaml(path: Path, *, strict: bool = False) -> dict[str, Any]:
    """Load YAML file."""
    if not strict and not path.exists():
        return {}

    try:
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)
        if strict and data is not None and not isinstance(data, dict):
            raise TypeError("exposure config must be an object")
        return data or {}
    except FileNotFoundError:
        return {}
    except ImportError as exc:
        if strict:
            raise ValueError("exposure configuration requires PyYAML") from exc
        # Fallback: basic YAML parsing for simple configs
        content = path.read_text()
        # Very basic parsing - handles simple key: value pairs
        result: dict[str, Any] = {}
        current_key = None
        current_list: list[Any] = []

        for line in content.split("\n"):
            line = line.rstrip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("  - "):
                # List item
                current_list.append(line[4:].strip())
            elif line.startswith("  "):
                # Nested dict item - skip for basic parsing
                continue
            elif ":" in line:
                if current_key and current_list:
                    result[current_key] = current_list
                    current_list = []
                key, val = line.split(":", 1)
                current_key = key.strip()
                val = val.strip()
                if val:
                    result[current_key] = val
        if current_key and current_list:
            result[current_key] = current_list
        return result
    except Exception as exc:
        if strict:
            raise ValueError("cannot read exposure configuration") from exc
        return {}
