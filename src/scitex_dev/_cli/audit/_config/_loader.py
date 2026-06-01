"""Loader + heuristic detector for `.scitex/dev/config.yaml`.

Schema (canonical): see GITIGNORED/RULES_FOR_SCIENTIFIC_PROJECTS.md
§"Project-type config".

```yaml
project-type:
  - pip          # PS-1xx rules apply
  - research     # RP1xx-RP9xx rules apply
audit:
  skip:
    - PS-108
  whitelist: .audit-whitelist.yaml
metadata:
  cohorts: 3
```

Both `project-type` keys can be present at once for hybrid repos
(a tool package whose `examples/` IS the research project).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PROJECT_TYPES = frozenset({"pip", "research", "special", "django", "deferred"})

CONFIG_REL_PATH = Path(".scitex/dev/config.yaml")


@dataclass(frozen=True)
class ProjectConfig:
    """Parsed `.scitex/dev/config.yaml`.

    `project_types` is always non-empty. `skip` holds rule codes the user
    pre-approved as exceptions. `whitelist_path` (if set) is resolved
    relative to the project root by callers.
    """

    project_types: frozenset[str]
    skip: frozenset[str] = frozenset()
    whitelist_path: Path | None = None
    metadata: dict = field(default_factory=dict)
    source: str = "config"  # "config" | "heuristic" | "override"

    def applies(self, code: str) -> bool:
        """True iff a rule code's family is active for this project.

        `special`-typed projects opt out of PS-103 (root-layout
        whitelist) — their unusual root organisation is by design
        (research-style numbered manuscript dirs, CMS content trees,
        etc.). All other PS rules still apply if `pip` is also listed.
        """
        # Three project-types opt out of PS-103 (root whitelist) with
        # different semantic intent:
        #
        #   special  — by-design unconventional layout (research trees,
        #              CMS content, multi-pkg monorepo, npm hybrid).
        #              No future cleanup expected.
        #   django   — Django framework canonical layout (apps/, static/,
        #              media/, templates/, …). Semantic alias of special.
        #   deferred — "I know this is messy; remind me later." The
        #              auditor opts out of the rule but emits a warning
        #              listing what would have fired so the operator has
        #              a TODO list ready when revisiting.
        if code == "PS-103" and self.project_types & {
            "special",
            "django",
            "deferred",
        }:
            return False
        # PS-173 (ADR format) is cross-cutting — ADRs are an ecosystem
        # convention for ALL project kinds (package / research / grant /
        # draft), not just pip packages. It only fires when docs/adr/
        # exists, so applying it everywhere costs nothing for repos
        # without ADRs.
        if code == "PS-173":
            return True
        # PS-PATH-* / PS-CLEW-* / PS-AGENT-* — paper-scitex-clew MVP
        # lint rules (PR #97, operator directive 2026-06-01). They
        # target research-project artifacts (`config/PATH.yaml`,
        # `scripts/agent/*.py`, `clew.add_claim` call sites) but the
        # SciTeX hybrid pattern lets these coexist with `pip` projects
        # too. Each rule is already artifact-gated (only fires when
        # the relevant file exists), so applying it cross-cutting is
        # safe and costs nothing for unrelated repos.
        if (
            code.startswith("PS-PATH-")
            or code.startswith("PS-CLEW-")
            or code.startswith("PS-AGENT-")
        ):
            return True
        prefix = code[:2]
        if prefix == "PS":
            return "pip" in self.project_types
        if prefix == "RP":
            return "research" in self.project_types
        if prefix == "SK":
            return "pip" in self.project_types
        # Cross-cutting (license/CLA helpers etc.) — apply to all.
        return True


def _read_yaml(path: Path) -> dict | None:
    """Tiny YAML reader: returns dict or None if file missing/unreadable.

    Uses PyYAML if available; falls back to a minimal subset parser
    sufficient for this schema (lists of strings, scalar key:value pairs)
    so the auditor doesn't pull a hard dep on PyYAML.
    """
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        import yaml  # type: ignore[import-untyped]

        return yaml.safe_load(text) or {}
    except ImportError:
        return _minimal_yaml(text)


def _minimal_yaml(text: str) -> dict:
    """Subset YAML parser for our schema only — list-of-strings + key: value."""
    result: dict = {}
    stack: list[tuple[int, str, list | dict]] = [(0, "", result)]
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        s = line.strip()
        # Pop stack to current indent
        while stack and indent < stack[-1][0]:
            stack.pop()
        parent = stack[-1][2]
        if s.startswith("- "):
            value = s[2:].strip().strip('"').strip("'")
            if isinstance(parent, list):
                parent.append(value)
        elif ":" in s and isinstance(parent, dict):
            key, _, val = s.partition(":")
            key = key.strip()
            val = val.strip()
            if val == "":
                container: list = []
                parent[key] = container
                stack.append((indent + 2, key, container))
            else:
                parent[key] = val.strip('"').strip("'")
        # Else: ignore (multi-line strings, anchors not supported)
    return result


def detect_project_types(repo: Path) -> frozenset[str]:
    """Heuristic fallback when no config file exists.

    - has pyproject.toml + src/<pkg>/  → pip
    - has scripts/ + data/ + config/   → research
    - has both                          → {pip, research}
    """
    types: set[str] = set()
    if (repo / "pyproject.toml").is_file() and (repo / "src").is_dir():
        if any(
            (repo / "src" / d).is_dir() for d in (repo / "src").iterdir() if d.is_dir()
        ):
            types.add("pip")
    if (
        (repo / "scripts").is_dir()
        and (repo / "data").is_dir()
        and (repo / "config").is_dir()
    ):
        types.add("research")
    if not types:
        # Default: assume pip if there's any sign of a Python package.
        types.add("pip")
    return frozenset(types)


def load_config(
    repo: Path,
    *,
    override_types: list[str] | None = None,
) -> ProjectConfig:
    """Resolve the active config (lookup order matches the spec).

    1. CLI override (`override_types`)
    2. `<repo>/.scitex/dev/config.yaml`
    3. Heuristic detection (warns the caller via `source="heuristic"`)
    """
    if override_types:
        return ProjectConfig(
            project_types=frozenset(override_types),
            source="override",
        )

    cfg_path = repo / CONFIG_REL_PATH
    raw = _read_yaml(cfg_path)
    if raw and "project-type" in raw:
        types_raw = raw.get("project-type") or []
        if isinstance(types_raw, str):
            types_raw = [types_raw]
        types = frozenset(t for t in types_raw if t in PROJECT_TYPES)
        if types:
            audit = raw.get("audit") or {}
            skip = audit.get("skip") or []
            if isinstance(skip, str):
                skip = [skip]
            wl = audit.get("whitelist")
            return ProjectConfig(
                project_types=types,
                skip=frozenset(skip),
                whitelist_path=Path(wl) if wl else None,
                metadata=raw.get("metadata") or {},
                source="config",
            )

    return ProjectConfig(
        project_types=detect_project_types(repo),
        source="heuristic",
    )


def write_config(
    repo: Path,
    *,
    project_types: list[str] | None = None,
    overwrite: bool = False,
) -> Path:
    """Write `<repo>/.scitex/dev/config.yaml` with the heuristic guess
    (or the explicit list). Returns the absolute path written.

    Raises FileExistsError if the file already exists and overwrite=False.
    """
    target = repo / CONFIG_REL_PATH
    if target.exists() and not overwrite:
        raise FileExistsError(target)
    if not project_types:
        project_types = sorted(detect_project_types(repo))

    target.parent.mkdir(parents=True, exist_ok=True)
    body = "# scitex-dev project-type config\n"
    body += "# Drives which rule families the auditor applies.\n"
    body += "# See: scitex-dev ecosystem audit-project --help\n\n"
    body += "project-type:\n"
    for t in project_types:
        body += f"  - {t}\n"
    body += "\n# audit:\n#   skip:\n#     - PS-108\n"
    target.write_text(body)
    return target


__all__ = [
    "PROJECT_TYPES",
    "CONFIG_REL_PATH",
    "ProjectConfig",
    "detect_project_types",
    "load_config",
    "write_config",
]
