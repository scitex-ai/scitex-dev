"""Duplicate diagnostics identify real conflicting installation metadata."""

import re
from importlib.metadata import EntryPoint, distributions

import pytest

from scitex_dev._cli.audit._project._plugins import ProjectPluginError, _discover
from scitex_dev.linter._plugin_loader import LinterPluginError, load_plugins


@pytest.mark.parametrize(
    "group,value,discover,error",
    [
        ("scitex_dev.audit.project", "scitex_logging._audit_plugin:get_plugin", _discover, ProjectPluginError),
        ("scitex_dev.linter.plugins", "scitex_logging._linter_plugin:get_plugin", lambda points: load_plugins(entry_points_iter=lambda: points), LinterPluginError),
    ],
)
def test_conflicting_metadata_paths_are_reported(tmp_path, group, value, discover, error):
    # Arrange — actual importlib metadata, including a stale editable record.
    paths = [tmp_path / "scitex_logging-1.0.dist-info", tmp_path / "scitex_logging.egg-info"]
    for path in paths:
        path.mkdir()
        (path / "METADATA").write_text("Name: scitex-logging\nVersion: 1.0\n")
        (path / "PKG-INFO").write_text("Name: scitex-logging\nVersion: 1.0\n")
        (path / "entry_points.txt").write_text(f"[{group}]\nscitex-logging = {value}\n")
    points = [ep for dist in distributions(path=[str(tmp_path)]) for ep in dist.entry_points]
    # Act — duplicate discovery must still refuse to produce a partial bundle.
    expected = "(?s)(?=.*duplicate provider)" + "".join(
        f"(?=.*{re.escape(str(path))})" for path in paths
    )
    # Assert — refusal must identify both metadata locations.
    with pytest.raises(error, match=expected):
        discover(points)


def test_injected_entry_point_without_distribution_has_explicit_origin():
    # Arrange
    from scitex_dev._core._entry_point_origin import _entry_point_origin

    point = EntryPoint(name="owned", value="owned:plugin", group="owned")
    # Act
    origin = _entry_point_origin(point)
    # Assert
    assert origin == "metadata: <unavailable>"
