"""Pure-Python smoke tests for _agentic_testing (no `claude` CLI required)."""

from scitex_dev._agentic_testing import (
    EvalCase,
    TriggerResult,
    extract_viewed_paths,
)


def test_extract_viewed_paths_from_toolbox_shape():
    sample = {
        "content": [
            {"type": "text", "text": "ok"},
            {"type": "tool_use", "name": "view", "input": {"path": "/x/SKILL.md"}},
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/y/SKILL.md"}},
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
        ]
    }
    paths = extract_viewed_paths(sample)
    assert "/x/SKILL.md" in paths and "/y/SKILL.md" in paths
    assert len(paths) == 2


def test_trigger_result_pass_rate():
    case = EvalCase(id="x", query="q", expected_skill=None)
    r = TriggerResult(
        case=case, runs=[True, True, False], viewed_paths_per_run=[[], [], []]
    )
    assert r.pass_rate == 2 / 3 and r.passed
