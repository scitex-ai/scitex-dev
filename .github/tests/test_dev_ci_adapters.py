"""Exercise the actual YAML, shell bridges, and public callee source as data.

Run explicitly with unittest; these source controls require Node and do not join
the scientific pytest suite. They make no Actions, native runner, or image calls.
"""

import copy
import gzip
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / ".github/workflows/pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml"
AUDIT = ROOT / ".github/workflows/scitex-dev-quality-audit-on-ubuntu-latest.yml"
FIXTURE = Path(__file__).parent / "fixtures/dev-shared-ci-public-source.json.gz"
BASE = "f8de4d18dbfdda0d2a6df164d222b08b68454b16"
REVISION = "d7d96c34d68cdfbb5503a933591f7748b5aa30ee"
PINS = {
    "ci-sif-matrix.yml": "f2abf8459abf711beb25355061df43572e506ae1461ffaf62cdaab2b05abcce1",
    "quality-audit.yml": "f44a2e6b5c479c2975d1cedf66738fdbf402a74cf1d8e26340bb9895524e7b4a",
    "runner-admission.yml": "f2e92f6a50526c2133cd12ae7c5cbd98ce2922354bd85c628ca48aad4acc6d18",
}


def workflow(path):
    return yaml.safe_load(path.read_text())


def public_sources():
    return json.loads(gzip.decompress(FIXTURE.read_bytes()))


def node(source):
    return subprocess.run(
        ["node", "-"],
        input=source,
        text=True,
        capture_output=True,
        timeout=4,
        check=False,
    )


def bridge(job, values):
    return subprocess.run(
        ["/usr/bin/bash", "-c", job["steps"][0]["run"]],
        env={"PATH": "/usr/bin:/bin", **values},
        text=True,
        capture_output=True,
        timeout=4,
        check=False,
    )


class DevCIAdapters(unittest.TestCase):
    def test_complete_public_source_fixture_has_exact_reviewed_pins(self):
        # Arrange
        fixture = public_sources()

        # Act
        observed = {
            name: hashlib.sha256(row["source"].encode()).hexdigest()
            for name, row in fixture["files"].items()
        }

        # Assert
        self.assertEqual(fixture["revision"], REVISION)
        self.assertEqual(observed, PINS)
        self.assertEqual(
            {name: row["sha256"] for name, row in fixture["files"].items()}, PINS
        )

    def test_caller_uses_only_the_real_public_interface(self):
        # Arrange
        caller = workflow(MATRIX)["jobs"]["immutable-matrix"]
        callee = yaml.safe_load(
            public_sources()["files"]["ci-sif-matrix.yml"]["source"]
        )
        declaration = callee.get("on", callee.get(True))["workflow_call"]

        # Act
        extra_inputs = set(caller["with"]) - set(declaration["inputs"])
        extra_secrets = set(caller["secrets"]) - set(declaration["secrets"])

        # Assert
        self.assertEqual(extra_inputs, set())
        self.assertEqual(extra_secrets, set())
        self.assertEqual(caller["with"]["suite"], "matrix")
        self.assertEqual(
            caller["uses"],
            "scitex-ai/.github/.github/workflows/ci-sif-matrix.yml@main",
        )
        self.assertNotIn("runs-on", caller)
        self.assertNotEqual(caller["secrets"], "inherit")

    def test_actual_callee_keeps_all_minors_and_refuses_null_registration(self):
        # Arrange
        callee = yaml.safe_load(
            public_sources()["files"]["ci-sif-matrix.yml"]["source"]
        )
        script = callee["jobs"]["profile"]["steps"][0]["with"]["script"]
        contract = script.split("// BEGIN SIF_CONTRACT\n", 1)[1].split(
            "// END SIF_CONTRACT", 1
        )[0]
        invocation = """
for (const event of ['push', 'pull_request', 'schedule', 'workflow_dispatch']) {
  const actual = profileSelection('scitex-ai/scitex-dev', event, 'matrix');
  if (JSON.stringify(actual.versions) !== '["3.11","3.12","3.13"]')
    throw new Error('Dev-minors-changed');
  for (const native of [false, true]) {
    let reason = null;
    try { planFor('scitex-ai/scitex-dev', event, native); }
    catch (error) { reason = error.message; }
    if (reason !== 'image-unqualified') throw new Error('null-registration-not-refused');
  }
}
console.log('all-four-events-three-minors-null-image-refused');
"""

        # Act
        result = node(contract + invocation)

        # Assert
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(), "all-four-events-three-minors-null-image-refused"
        )

    def test_hosted_self_audit_preserves_every_original_step(self):
        # Arrange
        original = public_sources()["baseline_audit"]
        self.assertEqual(original["revision"], BASE)
        self.assertEqual(
            hashlib.sha256(original["source"].encode()).hexdigest(),
            "da8fa84caf844b902360cbb31025966a91f4ddd1bb6535519bf107ca0cd7e44b",
        )
        self.assertEqual(original["bytes"], len(original["source"].encode()))
        previous = yaml.safe_load(original["source"])["jobs"]["audit"]
        candidate = workflow(AUDIT)["jobs"]["workspace-audit"]

        # Act
        actual_steps = candidate["steps"][:-1]

        # Assert
        self.assertEqual(actual_steps, previous["steps"])
        self.assertEqual(candidate["timeout-minutes"], previous["timeout-minutes"])
        self.assertEqual(candidate["runs-on"], "ubuntu-latest")
        self.assertEqual(actual_steps[-1]["run"], previous["steps"][-1]["run"])
        self.assertEqual(
            candidate["steps"][-1]["run"],
            '"$RUNNER_TEMP/venv/bin/python" .github/tests/test_dev_ci_adapters.py -v',
        )

    def test_original_required_names_and_full_dependencies_are_preserved(self):
        # Arrange
        matrix = workflow(MATRIX)["jobs"]["test"]
        audit = workflow(AUDIT)["jobs"]["audit"]

        # Act
        required = matrix["strategy"]["matrix"]["python-version"]

        # Assert
        self.assertEqual(required, ["3.11", "3.12", "3.13"])
        self.assertEqual(
            matrix["name"], "pytest-matrix-on-ubuntu-py${{ matrix.python-version }}"
        )
        self.assertEqual(matrix["needs"], ["immutable-matrix", "matrix-evidence"])
        self.assertEqual(audit["needs"], ["workspace-audit"])
        for job in (matrix, audit):
            self.assertEqual(job["if"], "${{ always() }}")
            self.assertEqual(job["runs-on"], "ubuntu-latest")
            self.assertEqual(job["timeout-minutes"], 2)
            self.assertEqual(job["permissions"], {})
            self.assertNotIn("continue-on-error", job)
        self.assertFalse(matrix["strategy"]["fail-fast"])

    def test_real_matrix_shell_bridge_propagates_failure_cancel_skip_unknown(self):
        # Arrange
        job = workflow(MATRIX)["jobs"]["test"]
        success = {"FULL_MATRIX_RESULT": "success", "CHILD_EVIDENCE_RESULT": "success"}
        cases = [success]
        for key in success:
            for rejected in ("failure", "cancelled", "skipped", "", "unknown"):
                cases.append({**success, key: rejected})

        # Act
        results = [bridge(job, case) for case in cases]

        # Assert
        self.assertEqual(results[0].returncode, 0, results[0].stderr)
        for case, result in zip(cases[1:], results[1:]):
            with self.subTest(case=case):
                self.assertNotEqual(result.returncode, 0)

    def test_real_audit_shell_bridge_propagates_failure_cancel_skip_unknown(self):
        # Arrange
        job = workflow(AUDIT)["jobs"]["audit"]
        values = ("success", "failure", "cancelled", "skipped", "", "unknown")

        # Act
        results = [bridge(job, {"WORKSPACE_AUDIT_RESULT": value}) for value in values]

        # Assert
        self.assertEqual(results[0].returncode, 0, results[0].stderr)
        for value, result in zip(values[1:], results[1:]):
            with self.subTest(value=value):
                self.assertNotEqual(result.returncode, 0)

    def test_production_child_qualifier_requires_three_completed_real_gates(self):
        # Arrange
        script = workflow(MATRIX)["jobs"]["matrix-evidence"]["steps"][0]["with"][
            "script"
        ]
        qualifier = script.split("// BEGIN DEV_MATRIX_EVIDENCE\n", 1)[1].split(
            "// END DEV_MATRIX_EVIDENCE", 1
        )[0]
        steps = [
            {
                "name": name,
                "status": "completed",
                "conclusion": "success",
                "started_at": "2026-10-03T21:00:00Z",
                "completed_at": "2026-10-03T21:00:10Z",
            }
            for name in (
                "Verify source/runtime and acquire whole images",
                "Run the genuine full leaf SIF suite",
            )
        ]
        valid = [
            {
                "id": index + 1,
                "name": f"immutable-matrix / test-dev-py{minor}",
                "run_id": 123,
                "head_sha": "a" * 40,
                "status": "completed",
                "conclusion": "success",
                "steps": copy.deepcopy(steps),
            }
            for index, minor in enumerate(("3.11", "3.12", "3.13"))
        ]
        variants = {"missing-minor": valid[:-1], "duplicate-row": valid + [valid[0]]}
        mutations = (
            ("skipped-job", "conclusion", "skipped"),
            ("queued-job", "status", "queued"),
            ("foreign-run", "run_id", 124),
            ("foreign-head", "head_sha", "b" * 40),
            ("absent-steps", "steps", []),
            ("foreign-caller", "name", "other / test-dev-py3.11"),
            ("duplicate-id", "id", 2),
        )
        for label, key, value in mutations:
            rows = copy.deepcopy(valid)
            rows[0][key] = value
            variants[label] = rows
        for label, key, value in (
            ("skipped-gate", "conclusion", "skipped"),
            ("missing-completion", "completed_at", None),
        ):
            rows = copy.deepcopy(valid)
            rows[0]["steps"][1][key] = value
            variants[label] = rows
        invocation = (
            "const good = " + json.dumps(valid) + ";\n"
            "const cases = " + json.dumps(variants) + ";\n"
            "if (qualifyChildren(good, 123, 'a'.repeat(40)).length !== 3) "
            "throw new Error('positive-inventory-refused');\n"
            "for (const [name, rows] of Object.entries(cases)) {\n"
            "  let refused = false;\n"
            "  try { qualifyChildren(rows, 123, 'a'.repeat(40)); }\n"
            "  catch (error) { refused = true; }\n"
            "  if (!refused) throw new Error('counterexample-accepted: ' + name);\n"
            "}\nconsole.log(JSON.stringify(Object.keys(cases)));\n"
        )

        # Act
        result = node(qualifier + invocation)

        # Assert
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(json.loads(result.stdout)), set(variants))

    def test_evidence_reader_is_current_attempt_readonly_and_bounded(self):
        # Arrange
        job = workflow(MATRIX)["jobs"]["matrix-evidence"]
        step = job["steps"][0]
        script = step["with"]["script"]

        # Act
        request_lines = [
            line.strip() for line in script.splitlines() if "GET /repos/" in line
        ]

        # Assert
        self.assertEqual(job["permissions"], {"actions": "read"})
        self.assertEqual(job["if"], "${{ always() }}")
        self.assertEqual(job["runs-on"], "ubuntu-latest")
        self.assertEqual(job["timeout-minutes"], 2)
        self.assertEqual(
            request_lines,
            [
                "'GET /repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt_number}/jobs', {"
            ],
        )
        self.assertIn("page <= 2", script)
        self.assertIn("per_page: 100, page, request: {timeout: 10000}", script)
        self.assertNotIn("github.paginate", script)
        self.assertEqual(step["env"]["ATTEMPT"], "${{ github.run_attempt }}")
        self.assertEqual(
            step["env"]["EXPECTED_HEAD"],
            "${{ github.event.pull_request.head.sha || github.sha }}",
        )


if __name__ == "__main__":
    unittest.main()
