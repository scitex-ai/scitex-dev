from pathlib import Path

from scitex_dev.ci.runner._storage import assess_storage


def test_assessment_refuses_non_runner_directory(tmp_path: Path):
    source = tmp_path / "runner"
    destination = tmp_path / "capacity" / "runner"
    source.mkdir()

    result = assess_storage(source, destination)

    check = next(c for c in result.checks if c.name == "runner_identity")
    assert check.to_dict()["ok"] is False
    assert result.ok is False


def test_assessment_refuses_same_filesystem(tmp_path: Path):
    source = tmp_path / "runner"
    destination = tmp_path / "capacity" / "runner"
    source.mkdir()
    (source / ".runner").write_text("{}")

    result = assess_storage(source, destination)

    check = next(c for c in result.checks if c.name == "different_filesystem")
    assert check.to_dict()["ok"] is False
    assert "device" in check.detail


def test_assessment_refuses_nonempty_destination(tmp_path: Path, monkeypatch):
    source = tmp_path / "runner"
    destination = tmp_path / "capacity" / "runner"
    source.mkdir()
    (source / ".runner").write_text("{}")
    destination.mkdir(parents=True)
    (destination / "unexpected").write_text("data")
    real_stat = Path.stat

    class _Stat:
        st_dev = 2

    def fake_stat(path, *args, **kwargs):
        if Path(path) == destination.parent:
            return _Stat()
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fake_stat)
    result = assess_storage(source, destination)

    check = next(c for c in result.checks if c.name == "destination_empty")
    assert check.to_dict()["ok"] is False
