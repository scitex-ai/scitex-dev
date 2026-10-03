"""Actual docs/import YAML and shell admission controls, without CI effects.

Baselines are full Git bodies captured at the stated revision, so shallow public
checkouts need no historical Git object. The admission body is the complete
reviewed public d7 source. No repository install, image or membership API runs.
"""

import hashlib
import json
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BASE_REVISION = "b453ac735dfaf1ca728e5739040af04fbcfbbaee"
ADMISSION_REVISION = "d7d96c34d68cdfbb5503a933591f7748b5aa30ee"
ADMISSION_SHA256 = "f2e92f6a50526c2133cd12ae7c5cbd98ce2922354bd85c628ca48aad4acc6d18"
LABELS = ["self-hosted", "Linux", "X64", "scitex-org-cpu"]
NATIVE_DESTINATION = json.dumps(
    {"group": "Organization", "labels": LABELS}, separators=(",", ":")
)

BASELINES = {
    "rtd-sphinx-build-on-ubuntu-latest.yml": {
        "bytes": 3_291,
        "sha256": "d05c9a828e6f47a4fd7319cd42f1cd48506ad9a3ab9499bd61978777a8234328",
        "git_oid": "450efb3518746cb1e374f677b88f5dc957c660f3",
        "source": 'name: docs\n\non:\n  push:\n    branches: [main, develop]\n  pull_request:\n\njobs:\n  sphinx:\n    # Skip when HEAD is the bot\'s own previous docs auto-commit \u2014 breaks\n    # the infinite loop without using `[skip ci]`, which would also\n    # suppress the tag-push and release workflows when the auto-commit\n    # is the most recent commit on develop at release time.\n    if: "!contains(github.event.head_commit.message, \'docs(sphinx_html): refresh from CI build\')"\n    runs-on: ${{ fromJSON(vars.CI_RUNS_ON || \'["self-hosted","Linux","X64","scitex-ci"]\') }}\n    permissions:\n      contents: write\n    steps:\n      - uses: actions/checkout@v4\n        with:\n          fetch-depth: 0\n          token: ${{ secrets.GITHUB_TOKEN }}\n\n      - name: Use a job-owned Python tool cache\n        run: |\n          tool_cache="$RUNNER_TEMP/scitex-dev-docs-python-tools-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"\n          scitex_state="$RUNNER_TEMP/scitex-dev-docs-state-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"\n          mkdir -p "$tool_cache" "$scitex_state"\n          printf \'%s\\n\' "RUNNER_TOOL_CACHE=$tool_cache" \\\n            "AGENT_TOOLSDIRECTORY=$tool_cache" \\\n            "SCITEX_DIR=$scitex_state" >> "$GITHUB_ENV"\n\n      - uses: actions/setup-python@v5\n        with:\n          python-version: "3.11"\n\n      - name: Create per-job venv (self-hosted shared-cache isolation)\n        # Keep package dependencies separate from the owned base interpreter.\n        # GITHUB_PATH makes discovery use the job venv; explicit interpreter\n        # paths below keep install and Sphinx independent of later PATH edits.\n        run: |\n          python -m venv "$RUNNER_TEMP/venv"\n          echo "$RUNNER_TEMP/venv/bin" >> "$GITHUB_PATH"\n\n      - name: Install package + docs deps\n        run: \'"$RUNNER_TEMP/venv/bin/python" -m pip install -e ".[docs]"\'\n\n      - name: Build Sphinx HTML (warnings fail PRs only)\n        run: |\n          if [ "${{ github.event_name }}" = "pull_request" ]; then\n            "$RUNNER_TEMP/venv/bin/python" -m sphinx -W -b html docs/sphinx docs/sphinx/_build/html\n          else\n            "$RUNNER_TEMP/venv/bin/python" -m sphinx -b html docs/sphinx docs/sphinx/_build/html\n          fi\n\n      - name: Refresh src/scitex_dev/_sphinx_html/ (develop push only)\n        # main is PR-only \u2014 its _sphinx_html/ bundle arrives via the\n        # develop -> main PR. Direct bot-pushes to main are inhibited\n        # so the branch history stays linear-via-PR.\n        if: github.event_name == \'push\' && github.ref == \'refs/heads/develop\'\n        run: |\n          rm -rf src/scitex_dev/_sphinx_html\n          cp -rf docs/sphinx/_build/html src/scitex_dev/_sphinx_html\n          touch src/scitex_dev/_sphinx_html/.nojekyll\n\n      - name: Commit refreshed HTML if it changed (develop push only)\n        continue-on-error: true\n        if: github.event_name == \'push\' && github.ref == \'refs/heads/develop\'\n        run: |\n          if [ -n "$(git status --porcelain src/scitex_dev/_sphinx_html)" ]; then\n            git config user.name "github-actions[bot]"\n            git config user.email "41898282+github-actions[bot]@users.noreply.github.com"\n            git add src/scitex_dev/_sphinx_html\n            git commit -m "docs(sphinx_html): refresh from CI build"\n            git push\n          fi\n',
    },
    "import-smoke-on-ubuntu-py3-12.yml": {
        "bytes": 1_849,
        "sha256": "f82cd95783b85472c60b0f5ba94884f42de87e5acdc5bc03ae44f21d5b0ecaba",
        "git_oid": "d8cb845548552e9e44b3eb8181635dee974e60d5",
        "source": 'name: import-smoke\n\n# Catches "wheel installs but `import scitex_dev` blows up at runtime"\n# \u2014 separate from the full pytest suite so a broken entry-point fails\n# fast without paying for the matrix. Companion to `tests` \u2014 confirms\n# the bare package (no extras) is `pip install -e .`-able and\n# `import scitex_dev` succeeds. Catches `[project] dependencies`\n# drift that the test matrix masks because it installs `[all,dev]`.\n\non:\n  push:\n    branches: [main, develop]\n  pull_request:\n    branches: [main, develop]\n  schedule:\n    - cron: "0 17 * * *"  # nightly 17:00 UTC (~02:00 JST), off-peak\n  workflow_dispatch:\n\njobs:\n  install-check:\n    name: import-smoke-on-ubuntu-py3-12\n    runs-on: ${{ fromJSON(vars.CI_RUNS_ON || \'["self-hosted","Linux","X64","scitex-ci"]\') }}\n    steps:\n      # fetch-depth: 0 is REQUIRED \u2014 the same defect as the pytest-matrix\n      # workflow: a shallow clone hides the tags setuptools-scm derives the\n      # version from, the install resolves to `0.1.dev1+g<sha>`, and that string\n      # cannot satisfy scitex-cards\' `scitex-dev>=0.59.0` requirement.\n      - uses: actions/checkout@v4\n        with:\n          fetch-depth: 0\n      - name: Use a job-owned Python tool cache\n        run: |\n          tool_cache="$RUNNER_TEMP/scitex-dev-import-python-tools-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"\n          mkdir -p "$tool_cache"\n          printf \'%s\\n\' "RUNNER_TOOL_CACHE=$tool_cache" \\\n            "AGENT_TOOLSDIRECTORY=$tool_cache" >> "$GITHUB_ENV"\n      - uses: actions/setup-python@v5\n        with:\n          python-version: "3.12"\n      - name: Install (no extras)\n        run: |\n          python -m venv .venv\n          .venv/bin/pip install --upgrade pip\n          .venv/bin/pip install -e .\n      - name: Import smoke\n        run: .venv/bin/python -c "import scitex_dev; print(scitex_dev.__version__)"\n',
    },
}

ADMISSION_SOURCE = "name: organization runner admission\n\non:\n  workflow_call:\n    inputs:\n      runs_on:\n        type: string\n        required: false\n        default: '[\"ubuntu-latest\"]'\n    outputs:\n      runs_on:\n        value: ${{ jobs.admission.outputs.runs_on }}\n      native_authorized:\n        value: ${{ jobs.admission.outputs.native_authorized }}\n      reason:\n        value: ${{ jobs.admission.outputs.reason }}\n\njobs:\n  admission:\n    runs-on: ubuntu-latest\n    permissions: {}\n    timeout-minutes: 2\n    outputs:\n      runs_on: ${{ steps.select.outputs.runs_on }}\n      native_authorized: ${{ steps.select.outputs.native_authorized }}\n      reason: ${{ steps.select.outputs.reason }}\n    steps:\n      # No checkout, API credential, secret inheritance or caller-script execution.\n      # Private/unavailable membership is UNKNOWN and receives hosted CI.\n      - id: select\n        name: Select a runner from original event identity\n        env:\n          REPOSITORY: ${{ github.repository }}\n          ORIGINAL_ACTOR: ${{ github.actor }}\n          TRIGGERING_ACTOR: ${{ github.triggering_actor }}\n          EVENT_NAME: ${{ github.event_name }}\n          PR_AUTHOR: ${{ github.event.pull_request.user.login }}\n          HEAD_REPOSITORY: ${{ github.event.pull_request.head.repo.full_name }}\n          REQUESTED_RUNS_ON: ${{ inputs.runs_on }}\n        run: |\n          node <<'NODE'\n          const fs = require('node:fs');\n          const hosted = ['ubuntu-latest'];\n          const org = 'scitex-ai';\n          const write = (runsOn, authorized, reason) => {\n            fs.appendFileSync(process.env.GITHUB_OUTPUT,\n              `runs_on=${JSON.stringify(runsOn)}\\nnative_authorized=${authorized}\\nreason=${reason}\\n`);\n          };\n          write(hosted, false, 'membership-not-confirmed');\n          async function select() {\n            const env = process.env;\n            if (!/^scitex-ai\\/[A-Za-z0-9_.-]+$/i.test(env.REPOSITORY || '')) return;\n            if (!['push', 'pull_request', 'schedule', 'workflow_dispatch'].includes(env.EVENT_NAME)) return;\n            const subjects = [env.ORIGINAL_ACTOR, env.TRIGGERING_ACTOR];\n            if (env.EVENT_NAME === 'pull_request') {\n              if (!env.HEAD_REPOSITORY || env.HEAD_REPOSITORY.toLowerCase() !== env.REPOSITORY.toLowerCase()) {\n                write(hosted, false, 'fork-or-missing-origin');\n                return;\n              }\n              subjects.push(env.PR_AUTHOR);\n            }\n            const login = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/;\n            if (subjects.some(s => typeof s !== 'string' || !login.test(s))) return;\n            let requested;\n            try { requested = JSON.parse(env.REQUESTED_RUNS_ON || ''); } catch { return; }\n            if (typeof requested === 'string') requested = [requested];\n            if (!Array.isArray(requested) || !requested.length || requested.length > 12 ||\n                requested.some(s => typeof s !== 'string' || s.length > 80)) return;\n            const native = requested.includes('self-hosted');\n            const known = new Set(['self-hosted', 'Linux', 'X64', 'scitex-ci', 'scitex-org-cpu',\n              'scitex-local-cpu', 'scitex-docker', 'sac-control-plane',\n              'scitex-compute-02', 'scitex-compute-03', 'scitex-compute-04']);\n            if (native && (requested.some(s => !known.has(s)) ||\n                !requested.some(s => ['scitex-ci', 'scitex-org-cpu', 'scitex-local-cpu', 'scitex-docker'].includes(s)))) {\n              write(hosted, false, 'undeclared-native-destination');\n              return;\n            }\n            if (!native && requested.some(s => !/^(ubuntu|windows|macos)-(latest|[0-9]+(?:\\.[0-9]+)?(?:-arm64)?)$/.test(s))) return;\n            for (const subject of new Set(subjects.map(s => s.toLowerCase()))) {\n              const response = await fetch(`https://api.github.com/orgs/${org}/public_members/${encodeURIComponent(subject)}`, {\n                redirect: 'error', signal: AbortSignal.timeout(5000),\n                headers: {Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}\n              });\n              if (response.status !== 204) return;\n            }\n            // Group restriction is the server-side boundary. Labels only select\n            // hardware inside the declared organization group after admission.\n            write(native ? {group: 'Organization', labels: requested} : requested,\n              native, native ? 'confirmed-organization-members' : 'requested-hosted');\n          }\n          select().catch(() => { /* Fixed hosted outputs already exist; no error body is logged. */ });\n          NODE\n"


def workflow(name):
    return yaml.safe_load((ROOT / ".github/workflows" / name).read_text())


def original(name):
    return yaml.safe_load(BASELINES[name]["source"])


def guarded_jobs():
    for filename, job_id in (
        ("rtd-sphinx-build-on-ubuntu-latest.yml", "sphinx"),
        ("import-smoke-on-ubuntu-py3-12.yml", "install-check"),
    ):
        yield filename, job_id, workflow(filename)["jobs"][job_id]


def run_guard(job, **changes):
    values = {
        "RUNNER_ENVIRONMENT": "self-hosted",
        "NATIVE_AUTHORIZED": "true",
        "ADMISSION_REASON": "confirmed-organization-members",
        "ADMISSION_RUNS_ON": NATIVE_DESTINATION,
    }
    values.update(changes)
    return subprocess.run(
        ["/usr/bin/bash", "-c", job["steps"][0]["run"]],
        env={"PATH": "/usr/bin:/bin", **values},
        capture_output=True,
        text=True,
        timeout=3,
        check=False,
    )


class DevDocsImportAdmission(unittest.TestCase):
    def test_complete_original_source_bodies_match_sha256_pins(self):
        # Arrange
        rows = BASELINES
        # Act
        observed = {
            name: hashlib.sha256(row["source"].encode()).hexdigest()
            for name, row in rows.items()
        }
        # Assert
        assert observed == {name: row["sha256"] for name, row in rows.items()}

    def test_complete_original_source_bodies_match_git_blob_pins(self):
        # Arrange
        rows = BASELINES
        # Act
        observed = {
            name: hashlib.sha1(
                b"blob "
                + str(len(row["source"].encode())).encode()
                + b"\0"
                + row["source"].encode()
            ).hexdigest()
            for name, row in rows.items()
        }
        # Assert
        assert observed == {name: row["git_oid"] for name, row in rows.items()}

    def test_original_source_size_matches_full_baseline_inventory(self):
        # Arrange
        rows = BASELINES
        # Act
        observed = {name: len(row["source"].encode()) for name, row in rows.items()}
        # Assert
        assert observed == {name: row["bytes"] for name, row in rows.items()}

    def test_actual_public_admission_body_matches_exact_reviewed_pin(self):
        # Arrange
        source = ADMISSION_SOURCE
        # Act
        observed = hashlib.sha256(source.encode()).hexdigest()
        # Assert
        assert observed == ADMISSION_SHA256

    def test_actual_public_admission_declares_only_supported_runner_input(self):
        # Arrange
        callee = yaml.safe_load(ADMISSION_SOURCE)
        # Act
        inputs = callee.get("on", callee.get(True))["workflow_call"]["inputs"]
        # Assert
        assert set(inputs) == {"runs_on"}

    def test_actual_public_admission_exposes_the_three_consumed_outputs(self):
        # Arrange
        callee = yaml.safe_load(ADMISSION_SOURCE)
        # Act
        outputs = callee.get("on", callee.get(True))["workflow_call"]["outputs"]
        # Assert
        assert set(outputs) == {"runs_on", "native_authorized", "reason"}

    def test_actual_public_admission_is_hosted_before_native_selection(self):
        # Arrange
        callee = yaml.safe_load(ADMISSION_SOURCE)
        # Act
        destination = callee["jobs"]["admission"]["runs-on"]
        # Assert
        assert destination == "ubuntu-latest"

    def test_actual_public_admission_preserves_original_and_triggering_identity(self):
        # Arrange
        callee = yaml.safe_load(ADMISSION_SOURCE)
        keys = ("ORIGINAL_ACTOR", "TRIGGERING_ACTOR", "PR_AUTHOR", "HEAD_REPOSITORY")
        # Act
        environment = callee["jobs"]["admission"]["steps"][0]["env"]
        observed = {key: environment[key] for key in keys}
        # Assert
        assert observed == {
            "ORIGINAL_ACTOR": "${{ github.actor }}",
            "TRIGGERING_ACTOR": "${{ github.triggering_actor }}",
            "PR_AUTHOR": "${{ github.event.pull_request.user.login }}",
            "HEAD_REPOSITORY": "${{ github.event.pull_request.head.repo.full_name }}",
        }

    def test_both_callers_bind_exact_immutable_public_admission(self):
        # Arrange
        names = BASELINES
        # Act
        observed = {
            name: workflow(name)["jobs"]["runner-admission"]["uses"] for name in names
        }
        # Assert
        assert observed == {
            name: "scitex-ai/.github/.github/workflows/runner-admission.yml@"
            + ADMISSION_REVISION
            for name in names
        }

    def test_both_callers_send_array_labels_through_the_actual_public_interface(self):
        # Arrange
        names = BASELINES
        # Act
        observed = {
            name: {
                key: json.loads(value)
                for key, value in workflow(name)["jobs"]["runner-admission"][
                    "with"
                ].items()
            }
            for name in names
        }
        # Assert
        assert observed == {name: {"runs_on": LABELS} for name in names}

    def test_both_admission_callers_do_not_inherit_secrets(self):
        # Arrange
        names = BASELINES
        # Act
        observed = {
            name: workflow(name)["jobs"]["runner-admission"].get("secrets")
            for name in names
        }
        # Assert
        assert observed == {name: None for name in names}

    def test_every_original_trigger_is_preserved(self):
        # Arrange
        names = BASELINES
        # Act
        observed = {
            name: {key: value for key, value in workflow(name).items() if key != "jobs"}
            for name in names
        }
        expected = {
            name: {key: value for key, value in original(name).items() if key != "jobs"}
            for name in names
        }
        # Assert
        assert observed == expected

    def test_every_original_command_and_develop_only_write_step_is_preserved(self):
        # Arrange
        jobs = list(guarded_jobs())
        # Act
        observed = {name: job["steps"][1:] for name, _, job in jobs}
        expected = {
            name: original(name)["jobs"][job_id]["steps"] for name, job_id, _ in jobs
        }
        # Assert
        assert observed == expected

    def test_original_required_names_permissions_and_doc_loop_condition_are_preserved(
        self,
    ):
        # Arrange
        jobs = list(guarded_jobs())
        # Act
        observed = {
            name: {
                key: value
                for key, value in job.items()
                if key not in {"needs", "runs-on", "steps"}
            }
            for name, _, job in jobs
        }
        expected = {
            name: {
                key: value
                for key, value in original(name)["jobs"][job_id].items()
                if key not in {"runs-on", "steps"}
            }
            for name, job_id, _ in jobs
        }
        # Assert
        assert observed == expected

    def test_each_original_job_uses_only_the_qualified_runner_output(self):
        # Arrange
        jobs = list(guarded_jobs())
        # Act
        observed = {name: (job["needs"], job["runs-on"]) for name, _, job in jobs}
        # Assert
        assert observed == {
            name: (
                "runner-admission",
                "${{ fromJSON(needs.runner-admission.outputs.runs_on) }}",
            )
            for name, _, _ in jobs
        }

    def test_only_admission_and_the_original_job_are_declared(self):
        # Arrange
        jobs = list(guarded_jobs())
        # Act
        observed = {name: set(workflow(name)["jobs"]) for name, _, _ in jobs}
        # Assert
        assert observed == {
            name: {"runner-admission", job_id} for name, job_id, _ in jobs
        }

    def test_unconditional_first_guard_receives_authentic_runner_and_admission_outputs(
        self,
    ):
        # Arrange
        jobs = list(guarded_jobs())
        # Act
        observed = {
            name: {key: value for key, value in job["steps"][0].items() if key != "run"}
            for name, _, job in jobs
        }
        expected = {
            name: {
                "name": "Require company admission before native work",
                "env": {
                    "RUNNER_ENVIRONMENT": "${{ runner.environment }}",
                    "NATIVE_AUTHORIZED": "${{ needs.runner-admission.outputs.native_authorized }}",
                    "ADMISSION_REASON": "${{ needs.runner-admission.outputs.reason }}",
                    "ADMISSION_RUNS_ON": "${{ needs.runner-admission.outputs.runs_on }}",
                },
            }
            for name, _, _ in jobs
        }
        # Assert
        assert observed == expected

    def test_real_native_guard_accepts_exact_confirmed_company_destination(self):
        # Arrange
        jobs = list(guarded_jobs())
        # Act
        results = [run_guard(job) for _, _, job in jobs]
        # Assert
        assert [result.returncode for result in results] == [0, 0]

    def test_real_native_guard_refuses_unauthorized_unknown_or_nonmember(self):
        # Arrange
        cases = [
            {"NATIVE_AUTHORIZED": value} for value in ("false", "", "unknown", "TRUE")
        ]
        cases += [
            {"ADMISSION_REASON": value}
            for value in (
                "membership-not-confirmed",
                "fork-or-missing-origin",
                "",
                "requested-hosted",
            )
        ]
        # Act
        results = [
            run_guard(job, **case) for _, _, job in guarded_jobs() for case in cases
        ]
        # Assert
        assert all(result.returncode != 0 for result in results)

    def test_real_native_guard_refuses_wrong_group_labels_and_malformed_destination(
        self,
    ):
        # Arrange
        destinations = [
            json.dumps({"group": "default", "labels": LABELS}, separators=(",", ":")),
            json.dumps(
                {"group": "Organization", "labels": LABELS[:-1]}, separators=(",", ":")
            ),
            json.dumps(
                {"group": "Organization", "labels": LABELS + ["scitex-docker"]},
                separators=(",", ":"),
            ),
            json.dumps(LABELS, separators=(",", ":")),
            '["ubuntu-latest"]',
            "not-json",
            "",
        ]
        # Act
        results = [
            run_guard(job, ADMISSION_RUNS_ON=value)
            for _, _, job in guarded_jobs()
            for value in destinations
        ]
        # Assert
        assert all(result.returncode != 0 for result in results)

    def test_hosted_unknown_private_and_fork_admission_allows_full_original_checks(
        self,
    ):
        # Arrange
        reasons = ("membership-not-confirmed", "fork-or-missing-origin", "")
        jobs = list(guarded_jobs())
        # Act
        results = [
            run_guard(
                job,
                RUNNER_ENVIRONMENT="github-hosted",
                NATIVE_AUTHORIZED="false",
                ADMISSION_REASON=reason,
                ADMISSION_RUNS_ON='["ubuntu-latest"]',
            )
            for _, _, job in jobs
            for reason in reasons
        ]
        # Assert
        assert [result.returncode for result in results] == [0] * len(results)

    def test_real_guard_refuses_unknown_runner_environment(self):
        # Arrange
        values = ("", "unknown", "self_hosted", "other")
        # Act
        results = [
            run_guard(job, RUNNER_ENVIRONMENT=value)
            for _, _, job in guarded_jobs()
            for value in values
        ]
        # Assert
        assert all(result.returncode != 0 for result in results)

    def test_unknown_runner_refusal_has_fixed_safe_diagnostic(self):
        # Arrange
        values = ("", "unknown", "self_hosted", "other")
        # Act
        results = [
            run_guard(job, RUNNER_ENVIRONMENT=value)
            for _, _, job in guarded_jobs()
            for value in values
        ]
        # Assert
        assert {result.stderr.strip() for result in results} == {
            "Unknown runner environment refused"
        }


if __name__ == "__main__":
    unittest.main()
