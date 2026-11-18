"""Qualify numeric-only host IO context using owned files and real procfs."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from _dev_ci_node_probe import _host_io_pressure_snapshot, _numeric_io_pressure

SAMPLE = (
    "some avg10=5.12 avg60=6.17 avg300=8.44 total=123456\n"
    "full avg10=5.11 avg60=6.10 avg300=8.28 total=123450\n"
)


class DevCIIOPressure(unittest.TestCase):
    def test_numeric_fields_preserve_percentages_and_cumulative_microseconds(self):
        self.assertEqual(
            _numeric_io_pressure(SAMPLE),
            {
                "some": {"avg10": 5.12, "avg60": 6.17, "avg300": 8.44, "total": 123456},
                "full": {"avg10": 5.11, "avg60": 6.10, "avg300": 8.28, "total": 123450},
            },
        )

    def test_unknown_fields_and_rows_cannot_copy_private_text(self):
        value = SAMPLE.replace("total=123456", "total=123456 private=/owned/private")
        actual = _numeric_io_pressure(value + "private /owned/private\n")
        self.assertEqual(actual, _numeric_io_pressure(SAMPLE))
        self.assertNotIn("private", json.dumps(actual))

    def test_malformed_samples_are_unavailable_not_partial_or_zero(self):
        for value in [
            "",
            SAMPLE.splitlines()[0],
            SAMPLE + SAMPLE.splitlines()[0],
            SAMPLE.replace("avg10=5.12", "avg10=5.12 avg10=6.00"),
            SAMPLE.replace("avg10=5.12", "avg10"),
            SAMPLE.replace("avg10=5.12", "avg10=private-data"),
            SAMPLE.replace("avg10=5.12", "avg10=NaN"),
            SAMPLE.replace("avg10=5.12", "avg10=inf"),
            SAMPLE.replace("avg10=5.12", "avg10=-0.01"),
            SAMPLE.replace("avg10=5.12", "avg10=100.01"),
            SAMPLE.replace("total=123456", "total=-1"),
            SAMPLE.replace("total=123456", "total=1.5"),
            SAMPLE.replace("avg300=8.28 ", ""),
        ]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError) as refusal:
                    _numeric_io_pressure(value)
                self.assertEqual(str(refusal.exception), "IO pressure counters unavailable")
                self.assertNotIn("private-data", str(refusal.exception))

    def test_owned_file_reader_labels_host_scope_without_causal_claim(self):
        with tempfile.TemporaryDirectory(prefix="dev-psi-owned-") as folder:
            path = Path(folder) / "io"
            path.write_text(SAMPLE)
            actual = _host_io_pressure_snapshot(path)
        self.assertEqual(actual["counters"], _numeric_io_pressure(SAMPLE))
        self.assertIn("host-wide", actual["scope"])
        self.assertIn("not per-child", actual["scope"])
        self.assertIn("microseconds", actual["units"])

    def test_missing_file_reports_unavailability_without_fake_counters(self):
        with tempfile.TemporaryDirectory(prefix="dev-psi-owned-") as folder:
            actual = _host_io_pressure_snapshot(Path(folder) / "absent")
        self.assertEqual(actual["unavailable"], "FileNotFoundError")
        self.assertNotIn("counters", actual)

    def test_directory_reader_error_is_bounded_and_does_not_copy_path(self):
        with tempfile.TemporaryDirectory(prefix="dev-psi-private-") as folder:
            actual = _host_io_pressure_snapshot(Path(folder))
        self.assertIn("unavailable", actual)
        self.assertNotIn("counters", actual)
        self.assertNotIn(folder, repr(actual))

    def test_oversized_or_non_ascii_or_malformed_files_do_not_leak_text(self):
        with tempfile.TemporaryDirectory(prefix="dev-psi-owned-") as folder:
            path = Path(folder) / "io"
            for data in [
                (SAMPLE + " " * 4097).encode(),
                b"private-data\xff",
                SAMPLE.replace("avg10=5.12", "avg10=private-data").encode(),
            ]:
                with self.subTest(length=len(data)):
                    path.write_bytes(data)
                    actual = _host_io_pressure_snapshot(path)
                    self.assertIn("unavailable", actual)
                    self.assertNotIn("counters", actual)
                    self.assertNotIn("private-data", repr(actual))

    @unittest.skipUnless(
        sys.platform == "linux" and Path("/proc/pressure/io").is_file(),
        "Linux IO PSI interface unavailable",
    )
    def test_actual_host_io_snapshot_is_numeric_context_only(self):
        actual = _host_io_pressure_snapshot()
        self.assertEqual(set(actual["counters"]), {"some", "full"})
        self.assertIn("not per-child", actual["scope"])
        self.assertIn("not per-child", json.loads(json.dumps(actual))["scope"])
