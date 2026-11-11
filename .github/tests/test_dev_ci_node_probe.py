"""Use real, inert Node children to qualify deadline diagnostics."""

import json
import os
import subprocess
import unittest

from _dev_ci_node_probe import run_node


class DevCINodeProbe(unittest.TestCase):
    def test_success_preserves_both_output_streams_and_exit_code(self):
        # Arrange
        source = "console.log('stdout'); console.error('stderr');"
        # Act
        result = run_node(source)
        # Assert
        self.assertEqual(
            (result.returncode, result.stdout, result.stderr),
            (0, "stdout\n", "stderr\n"),
        )

    def test_failure_remains_an_unsuccessful_completed_process(self):
        # Arrange
        source = "console.error('refused'); process.exitCode = 3;"
        # Act
        result = run_node(source)
        # Assert
        self.assertEqual(
            (result.returncode, result.stdout, result.stderr), (3, "", "refused\n")
        )

    def test_timeout_preserves_exception_and_owned_child_snapshot(self):
        # Arrange
        source = "setTimeout(() => {}, 6000);"
        refusal = self.assertRaises(subprocess.TimeoutExpired)
        # Act
        with refusal:
            run_node(source)
        # Assert
        error = refusal.exception
        note = json.loads(error.__notes__[0])
        self.assertEqual(
            (
                error.timeout,
                error.cmd,
                note["requested_timeout_seconds"],
                note["sample"]["pid"],
                note["sample"]["parent_pid"],
            ),
            (4, ["node", "-"], 4, note["child_pid"], os.getpid()),
        )
