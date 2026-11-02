"""Five default source-binding findings through the existing project SPI."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover -- Python 3.10
    import tomli as tomllib

from . import _bindings
from ._source import SourceTree, UnprovenBinding

_INTERFACES = ("Python API", "CLI", "MCP", "Web API", "skills")
RULES = [
    (
        f"PS-IF-{number:03d}",
        "§2",
        f"Default {name} interface must have an owned source binding; runtime availability and operation parity are separate checks.",
        "E",
        f"interface-{slug}",
    )
    for number, name, slug in zip(
        range(1, 6), _INTERFACES, ("python", "cli", "mcp", "web", "skills")
    )
]
_REASONS = re.compile(
    r"^(todo|tbd|n/?a|none|legacy|not needed|optional|because)\W*$", re.IGNORECASE
)


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    line: int
    detail: str
    severity: str = "E"


def _modules(project):
    name = project.get("name", "")
    if not isinstance(name, str) or not name.strip():
        raise UnprovenBinding("pyproject [project].name is missing")
    modules = [name.replace("-", "_")]
    for group in ("scitex_dev.docs", "scitex_dev.skills"):
        points = project.get("entry-points", {}).get(group, {})
        if not isinstance(points, dict):
            continue
        for value in points.values():
            if isinstance(value, str) and ":" not in value and value not in modules:
                modules.append(value)
    return modules


def inspect_interfaces(repo: Path, *, overlays=None) -> list[Finding]:
    """Inspect one explicit source tree without package imports or servers."""
    repo = Path(repo).resolve()
    source = SourceTree(repo, overlays=overlays)
    path = repo / "pyproject.toml"
    # Non-package research trees are not package-interface candidates.
    if not source.exists(path) and not (overlays is not None and path.exists()):
        return []
    try:
        metadata = tomllib.loads(source.read(path))
        project = metadata.get("project")
        if not isinstance(project, dict):
            raise UnprovenBinding("package [project] metadata is missing")
        if not isinstance(project.get("entry-points", {}), dict):
            raise UnprovenBinding("project.entry-points must be a table")
        modules = _modules(project)
    except (OSError, UnicodeError, ValueError) as exc:
        return [
            Finding(
                rule[0], "pyproject.toml", 1, f"Cannot prove {label} binding: {exc}"
            )
            for rule, label in zip(RULES, _INTERFACES)
        ]
    checks = (
        lambda: _bindings.python_binding(source, modules),
        lambda: _bindings.cli_binding(source, project),
        lambda: _bindings.mcp_binding(source, modules),
        lambda: _bindings.web_binding(source, project),
        lambda: _bindings.skills_binding(source, project),
    )
    findings = []
    for rule, check in zip(RULES, checks):
        try:
            problem = check()
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            problem = f"Cannot prove interface binding ({type(exc).__name__}): {exc}"
        if problem:
            findings.append(Finding(rule[0], "pyproject.toml", 1, problem))
    return _exemptions(source, findings)


def _exemptions(source, findings):
    repo = source.repo
    from scitex_dev._cli.audit._config import (
        ProjectConfig,
        load_config,
        parse_exemptions,
    )
    from scitex_dev._cli.audit._config._exemptions import exemption_notice_applies

    config_path = repo / ".scitex" / "dev" / "config.yaml"
    if source.exists(config_path):
        try:
            source.read(config_path)
        except (OSError, ValueError) as exc:
            return [
                *findings,
                Finding(
                    RULES[0][0],
                    ".scitex/dev/config.yaml",
                    1,
                    f"Cannot verify narrow interface exemptions: {exc}",
                ),
            ]
    from yaml import YAMLError

    try:
        if source.overlays is None:
            config = load_config(repo)
        else:
            from yaml import safe_load

            raw = (
                safe_load(source.read(config_path))
                if source.exists(config_path)
                else {}
            )
            audit = (raw or {}).get("audit") or {}
            exemptions, errors = parse_exemptions(audit.get("exemptions"))
            config = ProjectConfig(
                project_types=frozenset({"pip"}),
                exemptions=exemptions,
                exemption_errors=errors,
            )
    except (OSError, ValueError, TypeError, AttributeError, YAMLError) as exc:
        return [
            *findings,
            Finding(
                RULES[0][0],
                ".scitex/dev/config.yaml",
                1,
                f"Cannot parse narrow interface exemptions ({type(exc).__name__})",
            ),
        ]
    out = []
    for rule, *_rest in RULES:
        for error in config.exemption_errors:
            if exemption_notice_applies(error, rule):
                out.append(Finding(rule, ".scitex/dev/config.yaml", 1, error))
    for finding in findings:
        exemption = config.exemption_for(finding.rule, finding.path, finding.line)
        if exemption is None:
            out.append(finding)
            continue
        reason = exemption.reason.strip()
        if len(reason) < 30 or _REASONS.fullmatch(reason):
            out.append(
                Finding(
                    finding.rule,
                    ".scitex/dev/config.yaml",
                    1,
                    "Interface exception needs a specific substantive reason of at least 30 characters; the missing binding remains an error",
                )
            )
            out.append(finding)
        else:
            out.append(
                Finding(
                    finding.rule,
                    finding.path,
                    finding.line,
                    f"Explicit interface exception: {reason}. Unimplemented: {finding.detail}",
                    "I",
                )
            )
    return out


def check_interfaces(repo, violation_cls, out):
    """Project SPI adapter; hooks invoke the identical pure source checker."""
    for finding in inspect_interfaces(repo):
        violation = violation_cls(
            finding.rule, f"{repo / finding.path}:{finding.line}", finding.detail
        )
        if finding.severity != "E":
            violation.severity_override = finding.severity
        out.append(violation)
