from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_pytest_matrix_runs_only_in_verified_sif():
    # Arrange
    workflow = (
        ROOT
        / ".github/workflows/pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml"
    ).read_text()

    # Act
    conditions = (
        "SCITEX_CI_SIF_SHA256" in workflow,
        "exec-in-sif.sh run-in-sif.sh" in workflow,
        "actions/setup-python" not in workflow,
        "pip install -e" not in workflow,
    )

    # Assert
    assert all(conditions)


def test_inner_runner_requires_postgres_and_full_extras():
    # Arrange
    runner = (ROOT / ".github/ci/run-in-sif.sh").read_text()

    # Act
    conditions = (
        "host binaries are not an allowed fallback" in runner,
        'target="$TMPDIR/site" -e ".[all,dev]"' in runner,
        'SCITEX_STORE_DSN="postgresql://postgres@${PGHOST_ENC}/postgres"' in runner,
        "readiness query" in runner,
        ' -e ".[dev]"' not in runner,
    )

    # Assert
    assert all(conditions)


def test_outer_runner_refuses_an_unverified_image():
    # Arrange
    wrapper = (ROOT / ".github/ci/exec-in-sif.sh").read_text()

    # Act
    conditions = (
        "SCITEX_CI_SIF_SHA256:?" in wrapper,
        "ACTUAL_SIF_SHA256" in wrapper,
        "CI SIF digest mismatch" in wrapper,
    )

    # Assert
    assert all(conditions)
