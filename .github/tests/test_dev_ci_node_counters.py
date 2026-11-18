"""Qualify numeric-only, direct-child Linux wait evidence without running CI."""

import os
import subprocess
import sys
import unittest

from _dev_ci_node_probe import _child_snapshot, _numeric_proc_snapshot


class DevCINodeCounters(unittest.TestCase):
    def test_schedstat_keeps_runtime_and_runqueue_wait_in_nanoseconds(self):
        self.assertEqual(
            _numeric_proc_snapshot("schedstat", "1000000 7000000 4\n"),
            {"runtime_ns": 1000000, "runqueue_wait_ns": 7000000, "timeslices": 4},
        )

    def test_io_keeps_only_documented_counters_not_unknown_fields(self):
        text = (
            "rchar: 101\nwchar: 202\nsyscr: 3\nsyscw: 4\n"
            "read_bytes: 4096\nwrite_bytes: 8192\ncancelled_write_bytes: 0\n"
            "private_path: /owned/private\n"
        )
        actual = _numeric_proc_snapshot("io", text)
        self.assertEqual(actual["rchar"], 101)
        self.assertEqual(actual["read_bytes"], 4096)
        self.assertEqual(actual["write_bytes"], 8192)
        self.assertEqual(len(actual), 7)
        self.assertNotIn("private_path", actual)
        self.assertNotIn("/owned/private", repr(actual))

    def test_malformed_or_incomplete_counters_are_unavailable_not_zero(self):
        complete_io = (
            "rchar: 1\nwchar: 2\nsyscr: 3\nsyscw: 4\n"
            "read_bytes: 5\nwrite_bytes: 6\ncancelled_write_bytes: 0\n"
        )
        for name, text in [
            ("schedstat", "1 2"),
            ("schedstat", "1 2 3 4"),
            ("schedstat", "1 -2 3"),
            ("schedstat", "1 private-data 3"),
            ("io", "rchar: 1\n"),
            ("io", "rchar: -1\n"),
            ("io", complete_io.replace("rchar: 1", "rchar: -1")),
            ("io", complete_io.replace("rchar: 1", "rchar: private-data")),
            ("io", complete_io + "rchar: 7\n"),
        ]:
            with self.subTest(name=name, text=text):
                with self.assertRaises(ValueError) as refusal:
                    _numeric_proc_snapshot(name, text)
                self.assertNotIn("private-data", str(refusal.exception))

    @unittest.skipUnless(sys.platform == "linux", "Linux procfs evidence")
    def test_absent_process_retains_unavailability_without_zero_counters(self):
        # Linux PID_MAX_LIMIT is below this value; no process data is read.
        actual = _child_snapshot(2**31)
        for name in ("schedstat", "io"):
            self.assertEqual(actual[name + "_unavailable"], "FileNotFoundError")
            self.assertNotIn(name, actual)

    @unittest.skipUnless(sys.platform == "linux", "Linux procfs evidence")
    def test_actual_owned_child_exposes_numeric_counters_and_identity(self):
        with subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.stdin.read()"],
            stdin=subprocess.PIPE,
        ) as child:
            try:
                actual = _child_snapshot(child.pid)
                self.assertEqual(actual["pid"], child.pid)
                self.assertEqual(actual["parent_pid"], os.getpid())
                for name, keys in [
                    ("schedstat", {"runtime_ns", "runqueue_wait_ns", "timeslices"}),
                    (
                        "io",
                        {
                            "rchar",
                            "wchar",
                            "syscr",
                            "syscw",
                            "read_bytes",
                            "write_bytes",
                            "cancelled_write_bytes",
                        },
                    ),
                ]:
                    self.assertEqual(set(actual[name]), keys)
                    self.assertTrue(
                        all(type(v) is int and v >= 0 for v in actual[name].values())
                    )
                self.assertIn("cumulative", actual["counter_limit"])
            finally:
                child.communicate(b"", timeout=4)
