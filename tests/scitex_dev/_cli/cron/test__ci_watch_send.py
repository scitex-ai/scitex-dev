"""CI sends discover approval before dispatch and never retry a submitted turn."""

import subprocess

import pytest

from scitex_dev._cli.cron._ci_watch_send import send_fix_turn

LEGACY_HELP = (
    "Usage: sac agents send [OPTIONS] NAME [PROMPT]\n\nOptions:\n  --help  Help.\n"
)


@pytest.mark.parametrize(
    ("option", "approval"),
    [
        ("", []),
        ("  --yes, -y  Approve.\n", ["--yes"]),
        ("  -y, --yes  Approve.\n", ["--yes"]),
    ],
)
def test_dispatch_uses_only_advertised_approval(option, approval):
    # Arrange
    calls = []
    help_text = LEGACY_HELP + option

    def runner(args, *, input_text):
        calls.append((args, input_text))
        return subprocess.CompletedProcess(args, 0, help_text, "")

    # Act
    send_fix_turn("worker", "--literal prompt", runner=runner)

    # Assert
    assert calls == [
        (["agents", "send", "--help"], ""),
        (["agents", "send", *approval, "--", "worker", "--literal prompt"], ""),
    ]


@pytest.mark.parametrize(
    ("exit_code", "help_text", "reason"),
    [
        (1, "", "cannot inspect"),
        (0, "unexpected output", "did not identify"),
        (0, "Usage: sac agents send [OPTIONS] NAME\n", "omitted its options"),
    ],
)
def test_failed_discovery_never_dispatches(exit_code, help_text, reason):
    # Arrange
    calls = []
    error = ""

    def runner(args, *, input_text):
        calls.append(args)
        return subprocess.CompletedProcess(args, exit_code, help_text, "")

    # Act
    try:
        send_fix_turn("worker", "bounded work", runner=runner)
    except RuntimeError as exc:
        error = str(exc)

    # Assert
    assert (reason in error, calls) == (True, [["agents", "send", "--help"]])


def test_prose_mention_does_not_advertise_an_approval_option():
    # Arrange
    calls = []
    help_text = LEGACY_HELP.replace(
        "\nOptions:", "\n  --yes is discussed here.\nOptions:"
    )

    def runner(args, *, input_text):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, help_text, "")

    # Act
    send_fix_turn("worker", "bounded work", runner=runner)

    # Assert
    assert calls[-1] == ["agents", "send", "--", "worker", "bounded work"]


def test_send_failure_is_returned_once_without_a_legacy_retry():
    # Arrange
    calls = []
    responses = iter(
        [
            subprocess.CompletedProcess([], 0, LEGACY_HELP + "  --yes  Approve.\n", ""),
            subprocess.CompletedProcess([], 1, "", "owned refusal"),
        ]
    )

    def runner(args, *, input_text):
        calls.append(args)
        return next(responses)

    # Act
    result = send_fix_turn("worker", "bounded work", runner=runner)

    # Assert
    assert (result.returncode, result.stderr, len(calls)) == (1, "owned refusal", 2)
