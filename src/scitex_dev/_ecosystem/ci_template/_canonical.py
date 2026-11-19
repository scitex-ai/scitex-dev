"""Recognize the owning template's complete static caller, not CI authority."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from ._workflows import CANONICAL_WORKFLOW

_MAX_BYTES = 65536


class _WorkflowLoader(yaml.SafeLoader):
    # Keep GitHub's `on` key a string without changing global SafeLoader rules.
    yaml_implicit_resolvers = {
        key: [(tag, pattern) for tag, pattern in entries
              if tag != "tag:yaml.org,2002:bool"]
        for key, entries in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }

    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise ValueError("workflow aliases are not recognized")
        return super().compose_node(parent, index)


def _mapping(loader, node):
    if not isinstance(node, yaml.MappingNode):
        raise ValueError("workflow mapping required")
    result = {}
    for key_node, value_node in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            raise ValueError("workflow merges are not recognized")
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise ValueError("workflow keys must be unique strings")
        result[key] = loader.construct_object(value_node)
    return result


def _boolean(loader, node):
    value = loader.construct_scalar(node).lower()
    if value not in {"true", "false"}:
        raise ValueError("workflow boolean must be true or false")
    return value == "true"


_WorkflowLoader.add_constructor("tag:yaml.org,2002:map", _mapping)
_WorkflowLoader.add_constructor("tag:yaml.org,2002:bool", _boolean)
_WorkflowLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$", re.IGNORECASE),
    list("tTfF"),
)


def _document(path):
    if path.is_symlink() or not path.is_file():
        return None
    with path.open("rb") as stream:
        body = stream.read(_MAX_BYTES + 1)
    if len(body) > _MAX_BYTES:
        return None
    document = yaml.load(body.decode("utf-8"), Loader=_WorkflowLoader)
    if not isinstance(document, dict):
        return None
    normalized = json.dumps(document, sort_keys=True, allow_nan=False)
    return document, normalized


def canonical_caller_job_ids(repo: Path) -> frozenset[str]:
    """Recognize only the complete bundled caller; unknown forms supply no jobs.

    Comments, layout and key order can vary. Duplicate keys, aliases, merges,
    symlinked workflow paths and oversized/unreadable input remain unrecognized.
    This checks static structure, not runner admission or execution/release
    qualification. No template, workflow, permissions or branch policy changes.
    """
    folder = repo / ".github" / "workflows"
    if (repo / ".github").is_symlink() or folder.is_symlink():
        return frozenset()
    template = Path(__file__).with_name("templates") / (CANONICAL_WORKFLOW + ".tmpl")
    try:
        actual, expected = _document(folder / CANONICAL_WORKFLOW), _document(template)
        if actual is None or expected is None or actual[1] != expected[1]:
            return frozenset()
        jobs = actual[0].get("jobs")
        return frozenset(jobs) if isinstance(jobs, dict) else frozenset()
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError, yaml.YAMLError):
        return frozenset()
