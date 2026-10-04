"""Exercise the real PostgreSQL capability boundary without starting a server."""

import hashlib
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "ci_postgres_capability", ROOT / ".github/ci/verify-postgres-capability.py"
)
CAPABILITY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CAPABILITY)


def capability_is_refused(operation):
    """Observe an actual capability refusal, preserving unexpected failures."""
    try:
        operation()
    except CAPABILITY.CapabilityError:
        return True
    return False


class PostgreSQLCapabilityTests(unittest.TestCase):
    """Run actual fake version executables, without starting PostgreSQL."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ci-pg-capability-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.binary_directory = self.root / "bin"
        self.binary_directory.mkdir()
        for tool in CAPABILITY.TOOLS:
            self.write_binary(
                tool, f'print({tool!r} + " (PostgreSQL) 16.15 (fixture)")'
            )

    def write_binary(self, tool, body):
        path = self.binary_directory / tool
        path.write_text("#!" + sys.executable + "\n" + body + "\n")
        path.chmod(0o700)
        return path

    def test_all_exact_binary_versions_are_established(self):
        # Arrange
        expected = {tool: "16.15" for tool in CAPABILITY.TOOLS}
        # Act
        result = CAPABILITY.verify_capability(self.binary_directory, "16.15")
        # Assert
        assert result["tools"] == expected

    def test_valid_literal_image_location_is_accepted(self):
        # Arrange
        location = "/usr/lib/postgresql/16/bin"
        # Act
        result = CAPABILITY.check_declared_location(location, "16.15")
        # Assert
        assert result is None

    def test_declared_major_version_mismatch_is_refused(self):
        # Arrange
        location = "/usr/lib/postgresql/18/bin"
        # Act
        refused = capability_is_refused(
            lambda: CAPABILITY.check_declared_location(location, "16.15")
        )
        # Assert
        assert refused

    def test_undeclared_home_binary_directory_is_refused(self):
        # Arrange
        location = "/home/user/postgres/16/bin"
        # Act
        refused = capability_is_refused(
            lambda: CAPABILITY.check_declared_location(location, "16.15")
        )
        # Assert
        assert refused

    def test_malformed_declared_version_is_refused(self):
        # Arrange
        version = "16.15; echo fallback"
        # Act
        refused = capability_is_refused(
            lambda: CAPABILITY.verify_capability(self.binary_directory, version)
        )
        # Assert
        assert refused

    def test_missing_binary_refuses_before_any_execution(self):
        # Arrange
        called = self.root / "called"
        for tool in CAPABILITY.TOOLS:
            self.write_binary(
                tool, f"from pathlib import Path; Path({str(called)!r}).touch()"
            )
        (self.binary_directory / "psql").unlink()
        # Act
        refused = capability_is_refused(
            lambda: CAPABILITY.verify_capability(self.binary_directory, "16.15")
        )
        # Assert
        assert (refused, called.exists()) == (True, False)

    def test_symlinked_binary_is_refused_before_execution(self):
        # Arrange
        (self.binary_directory / "psql").unlink()
        (self.binary_directory / "psql").symlink_to(self.binary_directory / "postgres")
        # Act
        refused = capability_is_refused(
            lambda: CAPABILITY.verify_capability(self.binary_directory, "16.15")
        )
        # Assert
        assert refused

    def test_symlinked_binary_directory_is_refused_before_execution(self):
        # Arrange
        alias = self.root / "alias"
        alias.symlink_to(self.binary_directory, target_is_directory=True)
        # Act
        refused = capability_is_refused(
            lambda: CAPABILITY.verify_capability(alias, "16.15")
        )
        # Assert
        assert refused

    def test_nonexecutable_version_binary_is_refused(self):
        # Arrange
        (self.binary_directory / "initdb").chmod(0o600)
        # Act
        refused = capability_is_refused(
            lambda: CAPABILITY.verify_capability(self.binary_directory, "16.15")
        )
        # Assert
        assert refused

    def test_different_server_minor_version_is_refused(self):
        # Arrange
        self.write_binary("postgres", 'print("postgres (PostgreSQL) 16.14")')
        # Act
        refused = capability_is_refused(
            lambda: CAPABILITY.verify_capability(self.binary_directory, "16.15")
        )
        # Assert
        assert refused

    def test_foreign_tool_label_is_refused(self):
        # Arrange
        self.write_binary("initdb", 'print("postgres (PostgreSQL) 16.15")')
        # Act
        refused = capability_is_refused(
            lambda: CAPABILITY.verify_capability(self.binary_directory, "16.15")
        )
        # Assert
        assert refused

    def test_multiline_version_output_is_refused(self):
        # Arrange
        self.write_binary("initdb", 'print("initdb (PostgreSQL) 16.15\\nextra output")')
        # Act
        refused = capability_is_refused(
            lambda: CAPABILITY.verify_capability(self.binary_directory, "16.15")
        )
        # Assert
        assert refused

    def test_failed_version_process_is_refused(self):
        # Arrange
        self.write_binary(
            "initdb", 'print("initdb (PostgreSQL) 16.15"); raise SystemExit(23)'
        )
        # Act
        refused = capability_is_refused(
            lambda: CAPABILITY.verify_capability(self.binary_directory, "16.15")
        )
        # Assert
        assert refused

    def test_oversized_version_output_is_refused_and_reaped(self):
        # Arrange
        binary = self.write_binary("initdb", 'print("x" * 4096)')
        # Act
        refused = capability_is_refused(lambda: CAPABILITY.version_output(binary))
        # Assert
        assert refused

    def test_timed_out_exact_process_incarnation_is_reaped(self):
        # Arrange
        receipt = self.root / "version-child.txt"
        binary = self.write_binary(
            "initdb",
            "import os, time; from pathlib import Path; "
            "pid = os.getpid(); "
            "birth = Path(f'/proc/{pid}/stat').read_text().rsplit(') ', 1)[1]"
            ".split()[19]; "
            f"Path({str(receipt)!r}).write_text(f'{{pid}} {{birth}}'); "
            "time.sleep(30)",
        )

        # Act
        reason = None
        try:
            # Exercise the production two-second budget. The actual child
            # publishes its own kernel identity before hanging; no launch hook
            # or substitute process implementation changes the boundary.
            CAPABILITY.version_output(binary)
        except CAPABILITY.CapabilityError as error:
            reason = str(error)
        pid, birth = receipt.read_text().split()
        stat_path = Path(f"/proc/{pid}/stat")
        current = (
            stat_path.read_text().rsplit(") ", 1)[1].split()[19]
            if stat_path.exists()
            else None
        )
        # Assert
        assert (reason, current == birth) == (
            "PostgreSQL version command timed out",
            False,
        )

    def test_private_environment_is_not_inherited_by_version_process(self):
        # Arrange
        self.write_binary(
            "initdb",
            'import os; print("initdb (PostgreSQL) 16.15" if '
            '"SCITEX_CAPABILITY_PRIVATE_SENTINEL" not in os.environ '
            'else "private leaked")',
        )
        previous = os.environ.get("SCITEX_CAPABILITY_PRIVATE_SENTINEL")
        os.environ["SCITEX_CAPABILITY_PRIVATE_SENTINEL"] = "fixture-only"
        # Act
        try:
            result = CAPABILITY.verify_capability(self.binary_directory, "16.15")
        finally:
            if previous is None:
                os.environ.pop("SCITEX_CAPABILITY_PRIVATE_SENTINEL", None)
            else:
                os.environ["SCITEX_CAPABILITY_PRIVATE_SENTINEL"] = previous
        # Assert
        assert result["tools"]["initdb"] == "16.15"


ORIGINAL_PG_SELECTION = (
    "mapfile -t PG_INITDB_CANDIDATES < <(compgen -G '/usr/li"
    "b/postgresql/*/bin/initdb' | sort -V)\n[ \"${#PG_INITDB_C"
    'ANDIDATES[@]}" -gt 0 ] || {\n    echo "::error::CI image'
    " lacks PostgreSQL server binaries under /usr/lib/postgr"
    "esql/*/bin. Rebuild and synchronize ci-cpu.sif; host bi"
    'naries are not an allowed fallback."\n    exit 1\n}\nPGBIN'
    '="$(dirname "${PG_INITDB_CANDIDATES[-1]}")"\nfor require'
    'd in initdb pg_ctl postgres; do\n    [ -x "$PGBIN/$requi'
    'red" ] || {\n        echo "::error::CI image PostgreSQL '
    "capability is incomplete: $PGBIN/$required is not execu"
    'table. Rebuild and synchronize ci-cpu.sif."\n        exi'
    't 1\n    }\ndone\nPSQL="$(command -v psql 2>/dev/null || t'
    'rue)"\n[ -x "$PSQL" ] || {\n    echo "::error::CI image P'
    "ostgreSQL capability is incomplete: psql is not executa"
    'ble. Rebuild and synchronize ci-cpu.sif."\n    exit 1\n}\n'
)
DECLARED_PG_SELECTION = (
    "# The central registered image profile declares these e"
    "xact capabilities.\n# No highest-version search, home bi"
    'nary or host fallback is accepted.\nPGBIN="${SCITEX_CI_P'
    "G_BIN:?registered image PostgreSQL directory is require"
    'd}"\nPG_CAPABILITY_VERSION="${SCITEX_CI_PG_VERSION:?regi'
    'stered image PostgreSQL version is required}"\nPSQL="$PG'
    'BIN/psql"\n'
)
CAPABILITY_PREFLIGHT = (
    "# Verify the declared image server/client closure in th"
    "e neutral environment,\n# before dependency resolution o"
    'r a test/plugin can run.\nscitex_release_run "$VENV/bin/'
    'python" -I -S -B \\\n    "$(dirname "${BASH_SOURCE[0]}")/'
    'verify-postgres-capability.py" \\\n    --bin-dir "$PGBIN"'
    ' --expected-version "$PG_CAPABILITY_VERSION"\n\n'
)
ORIGINAL_RUN_SHA256 = "a6a650ca320465884e42f9f1bc1699e46f9121caeb2c57a54c5e788eb04482ff"


class SourceCompositionTests(unittest.TestCase):
    """Preserve the full consumer body and the neutral pre-install boundary."""

    def test_only_reviewed_pg_seams_change_original_full_body(self):
        # Arrange
        text = (ROOT / ".github/ci/run-in-sif.sh").read_text()
        # Act
        restored = text.replace(DECLARED_PG_SELECTION, ORIGINAL_PG_SELECTION).replace(
            CAPABILITY_PREFLIGHT, ""
        )
        observed = hashlib.sha256(restored.encode()).hexdigest()
        # Assert
        assert (
            text.count(DECLARED_PG_SELECTION),
            text.count(CAPABILITY_PREFLIGHT),
            observed,
        ) == (1, 1, ORIGINAL_RUN_SHA256)

    def test_neutral_capability_check_precedes_full_installer_and_server(self):
        # Arrange
        text = (ROOT / ".github/ci/run-in-sif.sh").read_text()
        commands = [
            'scitex_release_context "$TMPDIR" "$VENV"',
            'scitex_release_run "$VENV/bin/python" -I -S -B',
            (
                'scitex_release_run uv pip install --python "$VENV/bin/python" '
                '--target="$TMPDIR/site" -e ".[all,dev]"'
            ),
            'scitex_release_run "$PGBIN/initdb"',
            'python -m pytest tests/ -n "$WORKERS" --dist load -q',
        ]
        # Act
        positions = [text.find(command) for command in commands]
        neutral_helper = CAPABILITY_PREFLIGHT in text
        # Assert
        assert (
            all(position >= 0 for position in positions),
            positions == sorted(positions),
            neutral_helper,
        ) == (True, True, True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
