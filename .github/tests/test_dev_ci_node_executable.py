"""Numeric executable identity without argv, paths, contents or Node warmup."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import _dev_ci_node_probe as probe


class DevCINodeExecutable(unittest.TestCase):
    def test_identity_does_not_open_executable_contents(self):
        with tempfile.TemporaryDirectory(prefix="private-exe-no-open-") as folder:
            target = (Path(folder) / "private-binary").resolve()
            target.write_bytes(b"private-content-never-open")

            def refuse_content_open(event, args):
                if (
                    event == "open"
                    and isinstance(args[0], str)
                    and Path(args[0]).resolve() == target
                ):
                    raise AssertionError("Executable contents were opened")

            sys.addaudithook(refuse_content_open)
            actual = probe._executable_identity(target)
            self.assertEqual(actual["status"], "available")
            self.assertEqual(actual["size_bytes"], 26)

    def test_owned_executable_link_reports_numeric_target_identity(self):
        with tempfile.TemporaryDirectory(prefix="private-exe-identity-") as folder:
            root = Path(folder)
            target = root / "private-binary-name"
            target.write_bytes(b"private-contents-sentinel")
            link = root / "exe"
            link.symlink_to(target)
            actual = probe._executable_identity(link)
            expected = target.stat()
            self.assertEqual(actual["status"], "available")
            self.assertEqual(actual["device_major"], os.major(expected.st_dev))
            self.assertEqual(actual["device_minor"], os.minor(expected.st_dev))
            self.assertEqual(actual["inode"], expected.st_ino)
            self.assertEqual(actual["size_bytes"], expected.st_size)
            self.assertEqual(actual["mtime_ns"], expected.st_mtime_ns)
            self.assertNotIn(folder, json.dumps(actual))
            self.assertNotIn(target.name, json.dumps(actual))
            self.assertNotIn("private-contents-sentinel", json.dumps(actual))

    def test_missing_identity_is_unavailable_not_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            actual = probe._executable_identity(Path(folder) / "absent")
        self.assertEqual(actual["status"], "unavailable")
        self.assertEqual(actual["unavailable"], "FileNotFoundError")
        self.assertNotIn("inode", actual)
        self.assertNotIn("size_bytes", actual)

    def test_dangling_link_does_not_expose_target_or_error_message(self):
        with tempfile.TemporaryDirectory(prefix="private-exe-target-") as folder:
            link = Path(folder) / "exe"
            link.symlink_to(Path(folder) / "private-target")
            actual = probe._executable_identity(link)
        self.assertEqual(actual["status"], "unavailable")
        self.assertNotIn(folder, json.dumps(actual))
        self.assertNotIn("private-target", json.dumps(actual))

    def test_directory_is_not_an_executable_file_identity(self):
        with tempfile.TemporaryDirectory(prefix="private-exe-directory-") as folder:
            actual = probe._executable_identity(Path(folder))
        self.assertEqual(actual["status"], "unavailable")
        self.assertNotIn("inode", actual)
        self.assertNotIn(folder, json.dumps(actual))

    @unittest.skipUnless(sys.platform == "linux", "Linux executable procfs identity")
    def test_actual_owned_child_identity_matches_kernel_executable(self):
        with subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.stdin.read()"],
            stdin=subprocess.PIPE,
        ) as child:
            try:
                actual = probe._executable_identity(
                    Path("/proc") / str(child.pid) / "exe"
                )
                expected = Path(sys.executable).stat()
                self.assertEqual(actual["status"], "available")
                self.assertEqual(actual["inode"], expected.st_ino)
                self.assertEqual(actual["size_bytes"], expected.st_size)
                self.assertEqual(
                    (actual["device_major"], actual["device_minor"]),
                    (os.major(expected.st_dev), os.minor(expected.st_dev)),
                )
                self.assertNotIn(sys.executable, json.dumps(actual))
                self.assertNotIn("stdin.read", json.dumps(actual))
                self.assertIn("not a root-cause verdict", actual["scope"])
            finally:
                child.communicate(b"", timeout=4)
