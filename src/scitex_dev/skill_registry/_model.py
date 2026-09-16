"""Domain records for harness-neutral SciTeX skill discovery."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class SkillRecord:
    """One valid package-local skill tree."""

    name: str
    owner: str
    path: Path
    skill_file: Path
    source_hash: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "owner": self.owner,
            "path": str(self.path),
            "skill_file": str(self.skill_file),
            "source_hash": self.source_hash,
        }


@dataclass(frozen=True)
class RegistryIssue:
    """A deterministic, adapter-independent registry finding."""

    code: str
    kind: str
    name: str
    path: Path
    message: str

    def to_dict(self) -> dict[str, str]:
        data = asdict(self)
        data["path"] = str(self.path)
        return data


@dataclass(frozen=True)
class RegistryReport:
    """Complete discovery result; invalid candidates are never omitted silently."""

    records: tuple[SkillRecord, ...]
    issues: tuple[RegistryIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues

    def require_valid(self) -> tuple[SkillRecord, ...]:
        if self.issues:
            detail = "; ".join(f"{item.code}:{item.name}" for item in self.issues)
            raise SkillRegistryError(f"skill registry is invalid: {detail}")
        return self.records

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": [item.to_dict() for item in self.records],
            "issues": [item.to_dict() for item in self.issues],
            "ok": self.ok,
        }


class SkillRegistryError(RuntimeError):
    """Raised when a caller requires a valid registry and findings exist."""


def sort_issues(issues: Iterable[RegistryIssue]) -> tuple[RegistryIssue, ...]:
    """Return findings in the stable order promised to adapters."""

    return tuple(
        sorted(
            issues,
            key=lambda item: (item.kind, item.name, str(item.path), item.code),
        )
    )


__all__ = [
    "RegistryIssue",
    "RegistryReport",
    "SkillRecord",
    "SkillRegistryError",
    "sort_issues",
]
