"""Dev-owned taxonomy is metadata, not discovery or live availability."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from scitex_dev.hierarchy import get_hierarchy_declarations, get_hierarchy_nodes


def _contract_present():
    try:
        return importlib.util.find_spec("scitex_sdk.hierarchy") is not None
    except ModuleNotFoundError as error:
        if error.name == "scitex_sdk":
            return False
        raise


def _load_result():
    try:
        nodes = get_hierarchy_nodes()
    except RuntimeError as error:
        return ("unavailable", str(error))
    return (
        "loaded",
        len(nodes),
        all(type(n).__module__ == "scitex_sdk.hierarchy" for n in nodes),
    )


def test_dev_declares_only_its_assigned_package_slot():
    # Arrange
    expected = [("package:scitex-dev", "3.4", "scitex.intermediate")]
    # Act
    rows = get_hierarchy_declarations()
    # Assert
    assert [(n["id"], n["index"], n["parent_id"]) for n in rows] == expected


def test_dev_does_not_claim_other_distributions():
    # Arrange
    rows = get_hierarchy_declarations()
    # Act
    distributions = [n["distribution"] for n in rows if "distribution" in n]
    # Assert
    assert distributions == ["scitex-dev"]


def test_callers_cannot_mutate_the_authoritative_declarations():
    # Arrange
    rows = get_hierarchy_declarations()
    rows[0]["label"] = "Changed by caller"
    # Act
    fresh = get_hierarchy_declarations()
    # Assert
    assert fresh[0]["label"] == "scitex-dev"


def test_plain_declarations_serialize_without_an_sdk_encoder():
    # Arrange
    rows = get_hierarchy_declarations()
    # Act
    decoded = json.loads(json.dumps(rows))
    # Assert
    assert decoded == list(rows)


def test_explicit_record_loading_matches_the_actual_sdk_capability():
    # Arrange
    expected = (
        ("loaded", 1, True)
        if _contract_present()
        else (
            "unavailable",
            (
                "Typed hierarchy records require the SDK hierarchy contract. "
                "Use get_hierarchy_declarations() to inspect metadata without it."
            ),
        )
    )
    # Act
    observed = _load_result()
    # Assert
    assert observed == expected


def test_plain_declaration_import_does_not_import_sdk(tmp_path):
    # Arrange
    root = Path(__file__).resolve().parents[3]
    env = dict(
        os.environ,
        PYTHONPATH=str(root / "src"),
        SCITEX_DIR=str(tmp_path / "state"),
        COVERAGE_FILE=str(tmp_path / "coverage"),
    )
    code = "from scitex_dev.hierarchy import get_hierarchy_declarations;import json,sys;print(json.dumps({'count':len(get_hierarchy_declarations()),'sdk_loaded':'scitex_sdk' in sys.modules}))"
    # Act
    result = subprocess.run(
        [sys.executable, "-B", "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    # Assert
    assert (result.returncode, json.loads(result.stdout)) == (
        0,
        {"count": 1, "sdk_loaded": False},
    )


def test_hierarchy_entry_point_is_declared_by_dev():
    # Arrange
    root = Path(__file__).resolve().parents[3]
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    # Act
    group = project["entry-points"]["scitex_dev.hierarchy"]
    # Assert
    assert group == {"scitex-dev": "scitex_dev.hierarchy:get_hierarchy_nodes"}
