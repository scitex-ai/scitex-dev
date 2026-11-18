"""Qualify bounded stage observations with real inert JavaScript children."""

import json
import subprocess
import unittest

from _dev_ci_callee_trace import (
    CAPTURE_LIMIT,
    PREFIX,
    STAGES,
    captured_callee_stages,
    traced_callee_source,
)
from _dev_ci_node_probe import run_node


class DevCICalleeTrace(unittest.TestCase):
    def test_success_preserves_stdout_and_reports_synchronous_stages(self):
        source = traced_callee_source("const value = 7;", "console.log(value);")
        result = run_node(source)
        self.assertEqual((result.returncode, result.stdout), (0, "7\n"))
        self.assertEqual(captured_callee_stages(result.stderr), list(STAGES))

    def test_contract_failure_does_not_claim_contract_loaded(self):
        source = traced_callee_source("throw Error('refused');", "console.log(7);")
        result = run_node(source)
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        self.assertEqual(captured_callee_stages(result.stderr), list(STAGES[:1]))

    def test_invocation_failure_does_not_claim_invocation_evaluated(self):
        source = traced_callee_source("const value = 7;", "throw Error('refused');")
        result = run_node(source)
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        self.assertEqual(captured_callee_stages(result.stderr), list(STAGES[:2]))

    def test_timeout_reports_stages_without_claiming_process_success(self):
        source = traced_callee_source("const value = 7;", "setTimeout(() => {}, 6000);")
        with self.assertRaises(subprocess.TimeoutExpired) as refusal:
            run_node(source)
        error = refusal.exception
        note = json.loads(error.__notes__[0])
        self.assertEqual(error.timeout, 4)
        self.assertEqual(note["callee_stages"], list(STAGES))
        self.assertIn("not process success", note["callee_stage_limit"])

    def test_parser_admits_only_exact_complete_known_lines(self):
        marker = PREFIX + STAGES[0]
        for value in (None, 123, {}, b"private-error-\xff\n", "private-error-漢\n"):
            with self.subTest(value=value):
                self.assertEqual(captured_callee_stages(value), [])
        for value in (marker, " " + marker + "\n", marker + "\r\n", marker + "-extra\n"):
            with self.subTest(value=value):
                self.assertEqual(captured_callee_stages(value), [])
        for value in (marker + "\nprivate-error-漢\n", (marker + "\n").encode()):
            with self.subTest(value=value):
                self.assertEqual(captured_callee_stages(value), [STAGES[0]])

    def test_parser_requires_newline_inside_capture_bound(self):
        marker = PREFIX + STAGES[0]
        for encode in (lambda text: text, lambda text: text.encode("ascii")):
            complete = "x" * (CAPTURE_LIMIT - len(marker) - 2) + "\n" + marker + "\n"
            truncated = "x" * (CAPTURE_LIMIT - len(marker) - 1) + "\n" + marker + "\n"
            late = "x" * CAPTURE_LIMIT + "\n" + marker + "\n"
            self.assertEqual(captured_callee_stages(encode(complete)), [STAGES[0]])
            self.assertEqual(captured_callee_stages(encode(truncated)), [])
            self.assertEqual(captured_callee_stages(encode(late)), [])
