#!/usr/bin/env python3
# Timestamp: 2026-07-21
# File: scitex_dev/_ecosystem/_registry_data_1.py

"""ECOSYSTEM table, part 1 of 2 ("scitex" .. "scitex-logging") — data only.

The table is split across two part modules purely to honor the
512-line file cap; ``_registry.py`` concatenates the parts, so the
combined dict's display order is part 1 followed by part 2. Keep
entries as literal dicts: ``scripts/quality/ecosystem_list.py``
regex-parses these files (no import), so a builder function or
loader indirection would silently break it. Prefer adding new
entries to part 2 unless display order dictates otherwise.
"""

ECOSYSTEM_PART_1 = {
    "scitex": {
        "local_path": "~/proj/scitex-python",
        "pypi_name": "scitex",
        "github_repo": "scitex-ai/scitex-python",
        "import_name": "scitex",
        "category": "umbrella",
    },
    "scitex-io": {
        "local_path": "~/proj/scitex-io",
        "pypi_name": "scitex-io",
        "github_repo": "scitex-ai/scitex-io",
        "import_name": "scitex_io",
        "category": "library",
    },
    "scitex-stats": {
        "local_path": "~/proj/scitex-stats",
        "pypi_name": "scitex-stats",
        "github_repo": "scitex-ai/scitex-stats",
        "import_name": "scitex_stats",
        "category": "library",
    },
    "scitex-clew": {
        "local_path": "~/proj/scitex-clew",
        "pypi_name": "scitex-clew",
        "github_repo": "scitex-ai/scitex-clew",
        "import_name": "scitex_clew",
        "category": "library",
    },
    "scitex-hub": {
        "local_path": "~/proj/scitex-hub",
        "pypi_name": "scitex-hub",
        "github_repo": "scitex-ai/scitex-hub",
        "import_name": "scitex_hub",
        "category": "library",
    },
    "figrecipe": {
        "local_path": "~/proj/figrecipe",
        "pypi_name": "figrecipe",
        "github_repo": "scitex-ai/figrecipe",
        "import_name": "figrecipe",
        "category": "external-lib",
    },
    "newb": {
        "local_path": "~/proj/newb",
        "pypi_name": "newb",
        "github_repo": "scitex-ai/newb",
        "import_name": "newb",
        "category": "external-lib",
    },
    "openalex-local": {
        "local_path": "~/proj/openalex-local",
        "pypi_name": "openalex-local",
        "github_repo": "scitex-ai/openalex-local",
        "import_name": "openalex_local",
        "category": "dataset",
    },
    "crossref-local": {
        "local_path": "~/proj/crossref-local",
        "pypi_name": "crossref-local",
        "github_repo": "scitex-ai/crossref-local",
        "import_name": "crossref_local",
        "category": "dataset",
    },
    "scitex-writer": {
        "local_path": "~/proj/scitex-writer",
        "pypi_name": "scitex-writer",
        "github_repo": "scitex-ai/scitex-writer",
        "import_name": "scitex_writer",
        "category": "library",
    },
    "scitex-dataset": {
        "local_path": "~/proj/scitex-dataset",
        "pypi_name": "scitex-dataset",
        "github_repo": "scitex-ai/scitex-dataset",
        "import_name": "scitex_dataset",
        "category": "library",
    },
    "socialia": {
        "local_path": "~/proj/socialia",
        "pypi_name": "socialia",
        "github_repo": "scitex-ai/socialia",
        "import_name": "socialia",
        "category": "external-lib",
    },
    "scitex-container": {
        "local_path": "~/proj/scitex-container",
        "pypi_name": "scitex-container",
        "github_repo": "scitex-ai/scitex-container",
        "import_name": "scitex_container",
        "category": "library",
    },
    "scitex-ssh": {
        "local_path": "~/proj/scitex-ssh",
        "pypi_name": "scitex-ssh",
        "github_repo": "scitex-ai/scitex-ssh",
        "import_name": "scitex_ssh",
        "category": "library",
    },
    "scitex-ui": {
        "local_path": "~/proj/scitex-ui",
        "pypi_name": "scitex-ui",
        "github_repo": "scitex-ai/scitex-ui",
        "import_name": "scitex_ui",
        "category": "library",
    },
    "scitex-app": {
        "local_path": "~/proj/scitex-app",
        "pypi_name": "scitex-app",
        "github_repo": "scitex-ai/scitex-app",
        "import_name": "scitex_app",
        "category": "library",
    },
    "scitex-audio": {
        "local_path": "~/proj/scitex-audio",
        "pypi_name": "scitex-audio",
        "github_repo": "scitex-ai/scitex-audio",
        "import_name": "scitex_audio",
        "category": "library",
    },
    "scitex-audit": {
        # Security audit orchestrator (bandit, shellcheck, pip-audit, GH
        # alerts). Added 2026-06-07 to close #132 — on PyPI and mounted
        # as ``scitex.audit`` (lazy_attr + ``[audit]`` extra) but missing
        # from this registry, so audit-all and umbrella-extras
        # reconciliation did not know about it.
        "local_path": "~/proj/scitex-audit",
        "pypi_name": "scitex-audit",
        # github_repo verified current 2026-07-21 (gh api): the GitHub
        # archive was NOT transferred to scitex-ai; still ywatanabe1989.
        "github_repo": "ywatanabe1989/scitex-audit",
        "import_name": "scitex_audit",
        "category": "library",
        # ARCHIVED 2026-07-16 (operator ruling). Content is in
        # scitex-security per ADR-0002, which reversed ADR-0001: security
        # is canonical; "audit" was the narrower, more ambiguous name and
        # collides with this package's own ``ecosystem audit-all`` verbs.
        # Nothing was ported -- security already carried every symbol;
        # audit's only unique ones were the ADR-0001-direction migration
        # helpers, i.e. the superseded half.
        #
        # The row STAYS rather than being deleted: the repo still exists
        # as a public GitHub archive and scitex-audit 0.2.0 is still
        # installable (archiving is not yanking; yanking breaks installed
        # callers per ADR-0002). Deleting it would blind ecosystem sweeps
        # to a repo that is still out there.
        "archived": True,
    },
    "scitex-parallel": {
        "local_path": "~/proj/scitex-parallel",
        "pypi_name": "scitex-parallel",
        "github_repo": "scitex-ai/scitex-parallel",
        "import_name": "scitex_parallel",
        "category": "library",
    },
    "scitex-types": {
        "local_path": "~/proj/scitex-types",
        "pypi_name": "scitex-types",
        "github_repo": "scitex-ai/scitex-types",
        "import_name": "scitex_types",
        "category": "library",
    },
    "scitex-path": {
        "local_path": "~/proj/scitex-path",
        "pypi_name": "scitex-path",
        "github_repo": "scitex-ai/scitex-path",
        "import_name": "scitex_path",
        "category": "library",
    },
    "scitex-repro": {
        "local_path": "~/proj/scitex-repro",
        "pypi_name": "scitex-repro",
        "github_repo": "scitex-ai/scitex-repro",
        "import_name": "scitex_repro",
        "category": "library",
    },
    "scitex-compat": {
        "local_path": "~/proj/scitex-compat",
        "pypi_name": "scitex-compat",
        "github_repo": "scitex-ai/scitex-compat",
        "import_name": "scitex_compat",
        "category": "library",
    },
    "scitex-etc": {
        "local_path": "~/proj/scitex-etc",
        "pypi_name": "scitex-etc",
        "github_repo": "scitex-ai/scitex-etc",
        "import_name": "scitex_etc",
        "category": "library",
    },
    "scitex-gists": {
        "local_path": "~/proj/scitex-gists",
        "pypi_name": "scitex-gists",
        "github_repo": "scitex-ai/scitex-gists",
        "import_name": "scitex_gists",
        "category": "library",
    },
    "scitex-db": {
        "local_path": "~/proj/scitex-db",
        "pypi_name": "scitex-db",
        "github_repo": "scitex-ai/scitex-db",
        "import_name": "scitex_db",
        "category": "library",
    },
    "scitex-scholar": {
        "local_path": "~/proj/scitex-scholar",
        "pypi_name": "scitex-scholar",
        "github_repo": "scitex-ai/scitex-scholar",
        "import_name": "scitex_scholar",
        "category": "library",
    },
    "scitex-seizure-metrics": {
        "local_path": "~/proj/scitex-seizure-metrics",
        "pypi_name": "scitex-seizure-metrics",
        "github_repo": "scitex-ai/scitex-seizure-metrics",
        "import_name": "scitex_seizure_metrics",
        "category": "library",
    },
    "scitex-template": {
        "local_path": "~/proj/scitex-template",
        "pypi_name": "scitex-template",
        "github_repo": "scitex-ai/scitex-template",
        "import_name": "scitex_template",
        "category": "template",
    },
    "scitex-dev": {
        "local_path": "~/proj/scitex-dev",
        "pypi_name": "scitex-dev",
        "github_repo": "scitex-ai/scitex-dev",
        "import_name": "scitex_dev",
        "category": "library",
    },
    "scitex-agent-container": {
        "local_path": "~/proj/scitex-agent-container",
        "pypi_name": "scitex-agent-container",
        "github_repo": "scitex-ai/scitex-agent-container",
        "import_name": "scitex_agent_container",
        "category": "library",
    },
    "scitex-orochi": {
        "local_path": "~/proj/scitex-orochi",
        "pypi_name": "scitex-orochi",
        "github_repo": "scitex-ai/scitex-orochi",
        "import_name": "scitex_orochi",
        "category": "library",
    },
    "scitex-str": {
        "local_path": "~/proj/scitex-str",
        "pypi_name": "scitex-str",
        "github_repo": "scitex-ai/scitex-str",
        "import_name": "scitex_str",
        "category": "library",
    },
    "scitex-logging": {
        "local_path": "~/proj/scitex-logging",
        "pypi_name": "scitex-logging",
        "github_repo": "scitex-ai/scitex-logging",
        "import_name": "scitex_logging",
        "category": "library",
    },
}


__all__ = ["ECOSYSTEM_PART_1"]


# EOF
