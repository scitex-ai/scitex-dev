"""Actual metadata accounting and upstream discovery behavior, without models."""

import asyncio
import copy
import json

import pytest
from click.testing import CliRunner
from fastmcp import Client, FastMCP

from scitex_dev import configure_mcp_discovery, measure_context


def test_unicode_counts_normalized_json_and_raw_instructions_without_echo():
    # Arrange
    snapshot = {
        "tools": [{"name": "provider_action", "description": "秘密 café"}],
        "skill_headers": [{"name": "owner/namespace/guide", "description": "Résumé"}],
        "instructions": "π\n",
    }
    original = copy.deepcopy(snapshot)
    encoded = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    # Act
    report = measure_context(**snapshot)
    # Assert
    assert (
        report["total"]
        == {"characters": len(encoded), "utf8_bytes": len(encoded.encode("utf-8"))}
        and report["instructions_raw"] == {"characters": 2, "utf8_bytes": 3}
        and report["instructions"] == {"characters": 5, "utf8_bytes": 6}
        and report["instructions_measurement"] == "serialized_json_string"
        and report["tokens"] is report["tokenizer"] is None
        and report["client_total_context"] == "not_observed"
        and "秘密" not in json.dumps(report, ensure_ascii=False)
        and "Résumé" not in json.dumps(report, ensure_ascii=False)
        and snapshot == original
    )


def test_explicit_attribution_does_not_infer_owners_from_names_or_headers():
    # Arrange
    tools = [{"name": "scitex_stats_hidden_owner"}, {"name": "opaque"}]
    headers = [{"name": "guide", "owner": "not-proof", "description": "selected only"}]
    # Act
    report = measure_context(
        tools=tools, skill_headers=headers, tool_owners={"opaque": "scitex-leaf"}
    )
    # Assert
    assert (
        [(row["owner"], row["ownership"]) for row in report["items"]]
        == [(None, "unattributed"), ("scitex-leaf", "declared"), (None, "unattributed")]
        and report["packages"]["unattributed"]["mcp_tools"] == 1
        and report["packages"]["unattributed"]["skill_headers"] == 1
        and report["packages"]["scitex-leaf"]["mcp_tools"] == 1
        and sum(row["utf8_bytes"] for row in report["packages"].values())
        < report["total"]["utf8_bytes"]
    )


@pytest.mark.parametrize("field", ["body", "content", "text", "instructions"])
def test_full_skill_body_fields_are_rejected(field):
    # Arrange
    headers = [{"name": "guide", field: "must not be loaded as a header"}]
    # Act
    # Assert
    with pytest.raises(ValueError, match="must not contain"):
        measure_context(skill_headers=headers)


@pytest.mark.parametrize("value", [None, "", " ", 7, "unattributed"])
def test_invalid_declared_owners_cannot_masquerade_as_known(value):
    # Arrange
    owners = {"tool": value}
    # Act
    # Assert
    with pytest.raises(ValueError, match="owner names"):
        measure_context(tools=[{"name": "tool"}], tool_owners=owners)


@pytest.mark.parametrize("kind", ["tools", "skill_headers"])
def test_duplicate_snapshot_identities_fail_instead_of_misattributing(kind):
    # Arrange
    payload = {kind: [{"name": "collision"}, {"name": "collision"}]}
    # Act
    # Assert
    with pytest.raises(ValueError, match="unique"):
        measure_context(**payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"tools": "not a list"},
        {"tools": ["not a mapping"]},
        {"tools": [{"name": " "}]},
        {"instructions": None},
        {"tools": [{"name": "bad", "value": float("nan")}]},
    ],
)
def test_malformed_or_non_json_metadata_is_a_visible_error(payload):
    # Arrange
    data = payload
    # Act
    # Assert
    with pytest.raises((TypeError, ValueError)):
        measure_context(**data)


def test_upstream_discovery_measures_advertised_tools_without_business_calls():
    # Arrange
    server = FastMCP("context fixture")
    business_calls = []

    def business():
        business_calls.append("invoked")
        return "not called by discovery"

    for index in range(50):
        server.tool(name=f"fixture_{index:03d}")(business)
    server.tool(name="fixture_disabled")(business)
    server.disable(names={"fixture_disabled"}, components={"tool"})

    async def exercise():
        async with Client(server) as client:
            baseline = await client.list_tools()
        configure_mcp_discovery(server, max_results=2)
        async with Client(server) as client:
            advertised = await client.list_tools()
            selected = await client.call_tool(
                "search_tools", {"pattern": "^fixture_017$"}
            )
            disabled = await client.call_tool(
                "search_tools", {"pattern": "fixture_disabled"}
            )
        report = measure_context(
            tools=[
                tool.model_dump(mode="json", by_alias=True, exclude_none=True)
                for tool in advertised
            ]
        )
        before = measure_context(
            tools=[
                tool.model_dump(mode="json", by_alias=True, exclude_none=True)
                for tool in baseline
            ]
        )
        return baseline, advertised, selected.data, disabled.data, report, before

    # Act
    baseline, advertised, selected, disabled, report, before = asyncio.run(exercise())
    # Assert
    assert (
        len(baseline) == 50
        and {tool.name for tool in advertised} == {"search_tools", "call_tool"}
        and [tool["name"] for tool in selected] == ["fixture_017"]
        and disabled == []
        and report["packages"]["unattributed"]["mcp_tools"] == 2
        and report["total"]["utf8_bytes"] < before["total"]["utf8_bytes"]
        and business_calls == []
    )


def test_standalone_cli_and_real_mcp_delegate_to_same_measurement():
    # Arrange
    from scitex_dev._cli._root import main
    from scitex_dev._mcp._server import mcp

    payload = {
        "tools": [{"name": "opaque", "description": "private text"}],
        "tool_owners": {"opaque": "owner"},
    }
    expected = measure_context(**payload)

    async def invoke_mcp():
        async with Client(mcp) as client:
            return (await client.call_tool("dev_context_measure", payload)).data

    # Act
    cli = CliRunner().invoke(
        main, ["context", "measure", "--json"], input=json.dumps(payload)
    )
    mcp_report = asyncio.run(invoke_mcp())
    # Assert
    assert cli.exit_code == 0 and json.loads(cli.output) == mcp_report == expected


def test_context_help_and_invalid_input_remain_visible():
    # Arrange
    from scitex_dev._cli._root import main

    runner = CliRunner()
    # Act
    help_result = runner.invoke(main, ["context", "measure", "--help"])
    invalid = runner.invoke(main, ["context", "measure"], input="[]")
    # Assert
    assert (
        help_result.exit_code == 0
        and "--input" in help_result.output
        and invalid.exit_code != 0
        and "JSON object" in invalid.output
    )


@pytest.mark.parametrize("limit", [0, -1, True, "2"])
def test_invalid_search_limits_fail_before_configuration(limit):
    # Arrange
    server = FastMCP("invalid config fixture")
    # Act
    # Assert
    with pytest.raises(ValueError, match="positive integer"):
        configure_mcp_discovery(server, max_results=limit)


def test_disabled_search_preserves_actual_upstream_catalog():
    # Arrange
    server = FastMCP("opt-out fixture")

    @server.tool()
    def existing_tool():
        return "business operation"

    async def advertised():
        async with Client(server) as client:
            return [tool.name for tool in await client.list_tools()]

    # Act
    configure_mcp_discovery(server, search=False)
    names = asyncio.run(advertised())
    # Assert
    assert names == ["existing_tool"]


def test_measurement_does_not_read_skill_bodies_files_or_client_state(tmp_path):
    # Arrange
    import os
    import subprocess
    import sys
    from pathlib import Path

    skill = tmp_path / "skill.md"
    skill.write_text("BODY_THAT_MUST_NOT_BE_LOADED")
    source = Path(__file__).resolve().parents[3] / "src"
    script = """
import sys,json
from scitex_dev import measure_context
attempts = []
def deny(event, args):
    if event in {"open", "os.listdir", "os.scandir", "subprocess.Popen",
                 "socket.connect", "socket.getaddrinfo"}:
        attempts.append(event)
        raise AssertionError("measurement must use supplied metadata only")
sys.addaudithook(deny)
r = measure_context(skill_headers=[{"name":"selected","path":sys.argv[1]}])
sys.stdout.write(json.dumps({"report":r,"attempts":attempts}))
"""
    env = dict(os.environ, PYTHONPATH=str(source), PYTHONDONTWRITEBYTECODE="1")
    # Act
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(skill)],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    # Assert
    assert (
        result.returncode == 0
        and json.loads(result.stdout)["attempts"] == []
        and "BODY_THAT_MUST_NOT_BE_LOADED" not in result.stdout
    ), result.stderr
