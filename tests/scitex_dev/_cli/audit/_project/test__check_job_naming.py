# -*- coding: utf-8 -*-
"""PS-226..PS-229 — the fleet-wide JobSpec declaration convention.

Every test asserts one thing (STX-TQ007), and the negative direction is
covered explicitly: a conforming provider must produce ZERO findings, because
a rule that fires on everything is indistinguishable from a rule that fires on
nothing.

The fixtures are REAL names measured across the fleet on 2026-08-11, not
invented ones — ``sac.accounts-refresh`` (the dotted timer that is the fleet's
sole OAuth refresher) and ``sac-listen`` (the hyphenated spelling sac's own
provider says the name MUST take if it is ever federated).

No mocks: every case writes a real ``src/<pkg>/`` tree under ``tmp_path`` and
runs the real check over it.
"""

from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._check_job_naming import (
    JOB_NAME_RE,
    JOB_NAMING_RULES,
    check_job_naming,
    expected_job_prefix,
)
from scitex_dev._cli.audit._project._violation import Violation

# --------------------------------------------------------------------- #
# Fixtures — real shapes                                                #
# --------------------------------------------------------------------- #

#: The dotted name that exists on the fleet today (sac's sole OAuth refresher).
DOTTED = """
from scitex_dev.jobs import JobSpec


def provide_jobs():
    return [
        JobSpec(
            name="sac.accounts-refresh",
            kind="timer",
            schedule="0 */2 * * *",
            command="sac accounts refresh --all",
            description="Rotate stored OAuth access tokens.",
            on_unit_active_sec="2h",
        ),
    ]
"""

#: The hyphenated, package-qualified spelling the convention asks for.
CONFORMING = """
from scitex_dev.jobs import JobSpec


def provide_jobs():
    return [
        JobSpec(
            name="scitex-agent-container-accounts-refresh",
            kind="timer",
            schedule="0 */2 * * *",
            command="sac accounts refresh --all",
            description="Rotate stored OAuth access tokens.",
            on_unit_active_sec="2h",
        ),
    ]
"""

#: Hyphenated but NOT package-qualified — the spelling sac's own provider says
#: ``sac listen`` must take if it is ever federated. Charset-clean,
#: prefix-dirty.
HYPHENATED_UNQUALIFIED = """
from scitex_dev.jobs import JobSpec


def provide_jobs():
    return [
        JobSpec(
            name="sac-listen",
            kind="service",
            schedule="",
            command="sac listen",
            description="Fleet control-plane long-poll listener.",
            restart_policy="always",
        ),
    ]
"""

DISTRIBUTION = "scitex-agent-container"


def _make_repo(tmp_path: Path, distribution: str, body: str) -> Path:
    """Materialise a minimal ``src/<pkg>/`` checkout holding ``body``."""
    pkg = distribution.replace("-", "_")
    src = tmp_path / "src" / pkg
    src.mkdir(parents=True)
    (src / "_jobs_plugin.py").write_text(body, encoding="utf-8")
    return tmp_path


def _run(repo: Path, distribution: str) -> list:
    out: list = []
    check_job_naming(repo, distribution, Violation, out)
    return out


def _codes(out: list) -> list:
    return [v.rule for v in out]


def _detail_for(out: list, code: str) -> str:
    return next(v.detail for v in out if v.rule == code)


# --------------------------------------------------------------------- #
# PS-226 — charset                                                      #
# --------------------------------------------------------------------- #


def test_a_dotted_name_is_flagged(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path, DISTRIBUTION, DOTTED)

    # Act
    out = _run(repo, DISTRIBUTION)

    # Assert
    assert "PS-226" in _codes(out)


def test_the_dotted_finding_names_the_offending_job(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path, DISTRIBUTION, DOTTED)

    # Act
    detail = _detail_for(_run(repo, DISTRIBUTION), "PS-226")

    # Assert
    assert "sac.accounts-refresh" in detail


def test_the_dotted_finding_states_the_derived_unit_filename(tmp_path):
    # Arrange — a rule that says only "bad name" makes the next reader
    # re-derive WHY, so the message must carry the mechanism.
    repo = _make_repo(tmp_path, DISTRIBUTION, DOTTED)

    # Act
    detail = _detail_for(_run(repo, DISTRIBUTION), "PS-226")

    # Assert
    assert "sac.accounts-refresh.service" in detail


def test_the_dotted_finding_cites_the_unit_that_would_not_be_adopted(tmp_path):
    # Arrange — the concrete fleet incident is the hand-written
    # `sac-listen.service` a dotted `sac.listen` would fail to adopt.
    repo = _make_repo(tmp_path, DISTRIBUTION, DOTTED)

    # Act
    detail = _detail_for(_run(repo, DISTRIBUTION), "PS-226")

    # Assert
    assert "sac-listen.service" in detail


def test_the_dotted_finding_offers_the_hyphenated_rename(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path, DISTRIBUTION, DOTTED)

    # Act
    detail = _detail_for(_run(repo, DISTRIBUTION), "PS-226")

    # Assert
    assert "sac-accounts-refresh" in detail


def test_the_dotted_finding_states_the_migration_ordering(tmp_path):
    # Arrange — install-before-uninstall is the failure mode; the message
    # must say so, because the rename is what the rule provokes.
    repo = _make_repo(tmp_path, DISTRIBUTION, DOTTED)

    # Act
    detail = _detail_for(_run(repo, DISTRIBUTION), "PS-226")

    # Assert
    assert "stop-old" in detail


def test_the_dotted_finding_names_the_single_use_token_hazard(tmp_path):
    # Arrange — two racing refreshers revoke each other; the message must
    # carry that, since this exact job is the one it flags.
    repo = _make_repo(tmp_path, DISTRIBUTION, DOTTED)

    # Act
    detail = _detail_for(_run(repo, DISTRIBUTION), "PS-226")

    # Assert
    assert "SINGLE-USE" in detail


def test_the_finding_points_at_the_declaring_line(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path, DISTRIBUTION, DOTTED)

    # Act
    out = _run(repo, DISTRIBUTION)

    # Assert
    assert out[0].where.endswith("_jobs_plugin.py:7")


def test_an_underscore_name_is_flagged(tmp_path):
    # Arrange
    body = DOTTED.replace("sac.accounts-refresh", "sac_accounts_refresh")
    repo = _make_repo(tmp_path, DISTRIBUTION, body)

    # Act
    out = _run(repo, DISTRIBUTION)

    # Assert
    assert "PS-226" in _codes(out)


def test_an_uppercase_name_is_flagged(tmp_path):
    # Arrange
    body = DOTTED.replace("sac.accounts-refresh", "SAC-Accounts-Refresh")
    repo = _make_repo(tmp_path, DISTRIBUTION, body)

    # Act
    out = _run(repo, DISTRIBUTION)

    # Assert
    assert "PS-226" in _codes(out)


def test_a_conforming_provider_produces_no_findings_at_all(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path, DISTRIBUTION, CONFORMING)

    # Act
    out = _run(repo, DISTRIBUTION)

    # Assert
    assert out == []


# --------------------------------------------------------------------- #
# PS-227 — package qualification                                        #
# --------------------------------------------------------------------- #


def test_a_hyphenated_but_unqualified_name_raises_only_ps227(tmp_path):
    # Arrange — `sac-listen` is charset-clean; only the prefix is wrong.
    repo = _make_repo(tmp_path, DISTRIBUTION, HYPHENATED_UNQUALIFIED)

    # Act
    out = _run(repo, DISTRIBUTION)

    # Assert
    assert _codes(out) == ["PS-227"]


def test_ps227_names_the_expected_prefixed_form(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path, DISTRIBUTION, HYPHENATED_UNQUALIFIED)

    # Act
    detail = _detail_for(_run(repo, DISTRIBUTION), "PS-227")

    # Assert
    assert "scitex-agent-container-sac-listen" in detail


def test_a_dotted_name_does_not_also_raise_ps227(tmp_path):
    # Arrange — one finding per defect. A name that fails the charset has
    # not yet earned a prefix opinion; two findings for one edit is noise.
    repo = _make_repo(tmp_path, DISTRIBUTION, DOTTED)

    # Act
    out = _run(repo, DISTRIBUTION)

    # Assert
    assert _codes(out) == ["PS-226"]


@pytest.mark.parametrize(
    "distribution,expected",
    [
        ("scitex-agent-container", "scitex-agent-container-"),
        ("scitex-dev", "scitex-dev-"),
        ("scitex-cards", "scitex-cards-"),
        ("figrecipe", "scitex-figrecipe-"),
    ],
)
def test_expected_prefix_is_derived_from_the_distribution(distribution, expected):
    # Arrange
    dist = distribution

    # Act
    prefix = expected_job_prefix(dist)

    # Assert
    assert prefix == expected


# --------------------------------------------------------------------- #
# PS-228 — description                                                  #
# --------------------------------------------------------------------- #


def test_a_missing_description_is_flagged(tmp_path):
    # Arrange
    body = CONFORMING.replace(
        '            description="Rotate stored OAuth access tokens.",\n', ""
    )
    repo = _make_repo(tmp_path, DISTRIBUTION, body)

    # Act
    out = _run(repo, DISTRIBUTION)

    # Assert
    assert _codes(out) == ["PS-228"]


def test_an_empty_description_is_flagged(tmp_path):
    # Arrange
    body = CONFORMING.replace("Rotate stored OAuth access tokens.", "   ")
    repo = _make_repo(tmp_path, DISTRIBUTION, body)

    # Act
    out = _run(repo, DISTRIBUTION)

    # Assert
    assert _codes(out) == ["PS-228"]


def test_a_non_literal_description_is_accepted_not_guessed_at(tmp_path):
    # Arrange — a computed description is PRESENT; refusing to guess what it
    # evaluates to is the point (a finding nobody can act on trains readers
    # to ignore the rule).
    body = CONFORMING.replace(
        'description="Rotate stored OAuth access tokens.",',
        "description=_DESC,",
    )
    repo = _make_repo(tmp_path, DISTRIBUTION, body)

    # Act
    out = _run(repo, DISTRIBUTION)

    # Assert
    assert out == []


# --------------------------------------------------------------------- #
# PS-229 — kind vocabulary                                              #
# --------------------------------------------------------------------- #


def test_an_impossible_kind_is_flagged(tmp_path):
    # Arrange — the REAL historical bug: `systemd` is not a kind, and a
    # consumer filtering on it matched nothing while four timers ran.
    body = CONFORMING.replace('kind="timer"', 'kind="systemd"')
    repo = _make_repo(tmp_path, DISTRIBUTION, body)

    # Act
    out = _run(repo, DISTRIBUTION)

    # Assert
    assert _codes(out) == ["PS-229"]


@pytest.mark.parametrize("kind", ["service", "timer", "cron", "daemon", "periodic"])
def test_every_accepted_kind_spelling_is_clean(tmp_path, kind):
    # Arrange — the intent spellings normalise into the stored set, so the
    # auditor must not reject what the dataclass accepts.
    body = CONFORMING.replace('kind="timer"', f'kind="{kind}"')
    repo = _make_repo(tmp_path, DISTRIBUTION, body)

    # Act
    out = _run(repo, DISTRIBUTION)

    # Assert
    assert out == []


# --------------------------------------------------------------------- #
# Robustness — the check must never be the thing that breaks the audit  #
# --------------------------------------------------------------------- #


def test_a_repo_with_no_src_package_is_clean(tmp_path):
    # Arrange
    repo = tmp_path

    # Act
    out = _run(repo, DISTRIBUTION)

    # Assert
    assert out == []


def test_a_repo_with_no_jobspecs_is_clean(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path, "scitex-dev", "x = 1\n")

    # Act
    out = _run(repo, "scitex-dev")

    # Assert
    assert out == []


def test_an_unparseable_file_does_not_raise(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path, "scitex-dev", "def (((:\n")

    # Act
    out = _run(repo, "scitex-dev")

    # Assert
    assert out == []


def test_a_computed_name_is_skipped_rather_than_guessed_at(tmp_path):
    # Arrange
    body = CONFORMING.replace(
        'name="scitex-agent-container-accounts-refresh",', "name=_NAME,"
    )
    repo = _make_repo(tmp_path, DISTRIBUTION, body)

    # Act
    out = _run(repo, DISTRIBUTION)

    # Assert
    assert _codes(out) == []


def test_a_module_qualified_jobspec_call_is_still_recognised(tmp_path):
    # Arrange — `_jobs.JobSpec(...)` is how scitex-dev's own modules call it.
    body = DOTTED.replace("        JobSpec(", "        _jobs.JobSpec(")
    repo = _make_repo(tmp_path, DISTRIBUTION, body)

    # Act
    out = _run(repo, DISTRIBUTION)

    # Assert
    assert "PS-226" in _codes(out)


# --------------------------------------------------------------------- #
# Registry wiring — a declared-but-unregistered rule is a silent no-op  #
# --------------------------------------------------------------------- #


def test_every_declared_rule_is_registered_in_the_corpus():
    # Arrange — a rule the registry does not know renders as `[CODE §?]`
    # and falls back to the default W severity, silently defeating the E.
    from scitex_dev._cli.audit._project._registry import RULES

    # Act
    codes = [code for code, _sec, _msg, _sev, _slug in JOB_NAMING_RULES]

    # Assert
    assert all(code in RULES for code in codes)


@pytest.mark.parametrize(
    "code,severity",
    [("PS-226", "E"), ("PS-227", "W"), ("PS-228", "E"), ("PS-229", "E")],
)
def test_the_declared_severity_survives_registry_assembly(code, severity):
    # Arrange — severity for a co-located rule must live in the tuple; an
    # entry in `_SEVERITY_OVERRIDES` would be a silent no-op.
    from scitex_dev._cli.audit._project._registry import RULES

    # Act
    actual = RULES[code].severity

    # Assert
    assert actual == severity


# --------------------------------------------------------------------- #
# The regex itself                                                      #
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "name",
    ["ci-watch", "scitex-dev-ci-watch", "scitex-dev-ci-watch-v2", "sac-listen"],
)
def test_the_regex_accepts_a_hyphenated_lowercase_name(name):
    # Arrange
    candidate = name

    # Act
    matched = bool(JOB_NAME_RE.match(candidate))

    # Assert
    assert matched


@pytest.mark.parametrize(
    "name",
    [
        "sac.accounts-refresh",
        "sac_accounts_refresh",
        "SAC-listen",
        "-leading",
        "trailing-",
        "double--hyphen",
    ],
)
def test_the_regex_rejects_punctuation_and_case(name):
    # Arrange
    candidate = name

    # Act
    matched = bool(JOB_NAME_RE.match(candidate))

    # Assert
    assert not matched


# EOF
