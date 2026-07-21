#!/usr/bin/env python3
# Timestamp: 2026-07-21
# File: scitex_dev/_ecosystem/_registry_data_2.py

"""ECOSYSTEM table, part 2 of 2 ("scitex-dict" .. "scitex-web") — data only.

The table is split across two part modules purely to honor the
512-line file cap; ``_registry.py`` concatenates the parts, so the
combined dict's display order is part 1 followed by part 2. Keep
entries as literal dicts: ``scripts/quality/ecosystem_list.py``
regex-parses these files (no import), so a builder function or
loader indirection would silently break it. Prefer adding new
entries to part 2 unless display order dictates otherwise.
"""

ECOSYSTEM_PART_2 = {
    "scitex-dict": {
        "local_path": "~/proj/scitex-dict",
        "pypi_name": "scitex-dict",
        "github_repo": "scitex-ai/scitex-dict",
        "import_name": "scitex_dict",
        "category": "library",
    },
    "scitex-browser": {
        "local_path": "~/proj/scitex-browser",
        "pypi_name": "scitex-browser",
        "github_repo": "scitex-ai/scitex-browser",
        "import_name": "scitex_browser",
        "category": "library",
    },
    "scitex-config": {
        "local_path": "~/proj/scitex-config",
        "pypi_name": "scitex-config",
        "github_repo": "scitex-ai/scitex-config",
        "import_name": "scitex_config",
        "category": "library",
    },
    "scitex-context": {
        "local_path": "~/proj/scitex-context",
        "pypi_name": "scitex-context",
        "github_repo": "scitex-ai/scitex-context",
        "import_name": "scitex_context",
        "category": "library",
    },
    "scitex-events": {
        "local_path": "~/proj/scitex-events",
        "pypi_name": "scitex-events",
        "github_repo": "scitex-ai/scitex-events",
        "import_name": "scitex_events",
        "category": "library",
    },
    "scitex-hpc": {
        "local_path": "~/proj/scitex-hpc",
        "pypi_name": "scitex-hpc",
        "github_repo": "scitex-ai/scitex-hpc",
        "import_name": "scitex_hpc",
        "category": "library",
    },
    "scitex-decorators": {
        "local_path": "~/proj/scitex-decorators",
        "pypi_name": "scitex-decorators",
        "github_repo": "scitex-ai/scitex-decorators",
        "import_name": "scitex_decorators",
        "category": "library",
    },
    "scitex-pd": {
        "local_path": "~/proj/scitex-pd",
        "pypi_name": "scitex-pd",
        "github_repo": "scitex-ai/scitex-pd",
        "import_name": "scitex_pd",
        "category": "library",
    },
    "scitex-plt": {
        "local_path": "~/proj/scitex-plt",
        "pypi_name": "scitex-plt",
        "github_repo": "scitex-ai/scitex-plt",
        "import_name": "scitex_plt",
        "category": "library",
    },
    "scitex-nn": {
        "local_path": "~/proj/scitex-nn",
        "pypi_name": "scitex-nn",
        "github_repo": "scitex-ai/scitex-nn",
        "import_name": "scitex_nn",
        "category": "library",
    },
    "scitex-math": {
        # Mathematical utilities (parity helpers, etc.). Added
        # 2026-06-07 alongside scitex-audit (#132 batch) — on PyPI and
        # GH but was absent from this registry.
        "local_path": "~/proj/scitex-math",
        "pypi_name": "scitex-math",
        "github_repo": "scitex-ai/scitex-math",
        "import_name": "scitex_math",
        "category": "library",
    },
    "scitex-ml": {
        "local_path": "~/proj/scitex-ml",
        "pypi_name": "scitex-ml",
        "github_repo": "scitex-ai/scitex-ml",
        "import_name": "scitex_ml",
        "category": "library",
    },
    "scitex-genai": {
        "local_path": "~/proj/scitex-genai",
        "pypi_name": "scitex-genai",
        "github_repo": "scitex-ai/scitex-genai",
        "import_name": "scitex_genai",
        "category": "library",
    },
    "scitex-dsp": {
        "local_path": "~/proj/scitex-dsp",
        "pypi_name": "scitex-dsp",
        "github_repo": "scitex-ai/scitex-dsp",
        "import_name": "scitex_dsp",
        "category": "library",
    },
    "scitex-benchmark": {
        "local_path": "~/proj/scitex-benchmark",
        "pypi_name": "scitex-benchmark",
        "github_repo": "scitex-ai/scitex-benchmark",
        "import_name": "scitex_benchmark",
        "category": "library",
    },
    "scitex-bridge": {
        # GH-archived 2026 — cross-module adapter shim superseded by
        # inline integration in scitex-stats / scitex-plt. Kept in the
        # registry so historical refs resolve; auditors short-circuit
        # on archived=True.
        "local_path": "~/proj/scitex-bridge",
        "pypi_name": "scitex-bridge",
        # github_repo verified current 2026-07-21 (gh api): the GitHub
        # archive was NOT transferred to scitex-ai; still ywatanabe1989.
        "github_repo": "ywatanabe1989/scitex-bridge",
        "import_name": "scitex_bridge",
        "category": "library",
        "archived": True,
    },
    "scitex-capture": {
        "local_path": "~/proj/scitex-capture",
        "pypi_name": "scitex-capture",
        "github_repo": "scitex-ai/scitex-capture",
        "import_name": "scitex_capture",
        "category": "library",
    },
    "scitex-cv": {
        "local_path": "~/proj/scitex-cv",
        "pypi_name": "scitex-cv",
        "github_repo": "scitex-ai/scitex-cv",
        "import_name": "scitex_cv",
        "category": "library",
    },
    "scitex-datetime": {
        "local_path": "~/proj/scitex-datetime",
        "pypi_name": "scitex-datetime",
        "github_repo": "scitex-ai/scitex-datetime",
        "import_name": "scitex_datetime",
        "category": "library",
    },
    "scitex-git": {
        "local_path": "~/proj/scitex-git",
        "pypi_name": "scitex-git",
        "github_repo": "scitex-ai/scitex-git",
        "import_name": "scitex_git",
        "category": "library",
    },
    "scitex-introspect": {
        "local_path": "~/proj/scitex-introspect",
        "pypi_name": "scitex-introspect",
        "github_repo": "scitex-ai/scitex-introspect",
        "import_name": "scitex_introspect",
        "category": "library",
    },
    "scitex-linalg": {
        "local_path": "~/proj/scitex-linalg",
        "pypi_name": "scitex-linalg",
        "github_repo": "scitex-ai/scitex-linalg",
        "import_name": "scitex_linalg",
        "category": "library",
    },
    "scitex-msword": {
        "local_path": "~/proj/scitex-msword",
        "pypi_name": "scitex-msword",
        "github_repo": "scitex-ai/scitex-msword",
        "import_name": "scitex_msword",
        "category": "library",
    },
    "scitex-notebook": {
        "local_path": "~/proj/scitex-notebook",
        "pypi_name": "scitex-notebook",
        "github_repo": "scitex-ai/scitex-notebook",
        "import_name": "scitex_notebook",
        "category": "library",
    },
    "scitex-notification": {
        "local_path": "~/proj/scitex-notification",
        "pypi_name": "scitex-notification",
        "github_repo": "scitex-ai/scitex-notification",
        "import_name": "scitex_notification",
        "category": "library",
    },
    "scitex-os": {
        "local_path": "~/proj/scitex-os",
        "pypi_name": "scitex-os",
        "github_repo": "scitex-ai/scitex-os",
        "import_name": "scitex_os",
        "category": "library",
    },
    "scitex-repl": {
        # Interactive REPL helpers (embed, less, paste). Added
        # 2026-06-07 — shipped to PyPI as v0.1.1 on 2026-06-06
        # (alongside the scitex-math v0.1.x release wave).
        "local_path": "~/proj/scitex-repl",
        "pypi_name": "scitex-repl",
        "github_repo": "scitex-ai/scitex-repl",
        "import_name": "scitex_repl",
        "category": "library",
    },
    "scitex-resource": {
        "local_path": "~/proj/scitex-resource",
        "pypi_name": "scitex-resource",
        "github_repo": "scitex-ai/scitex-resource",
        "import_name": "scitex_resource",
        "category": "library",
    },
    "scitex-security": {
        # CANONICAL. This entry previously described the ADR-0001 (#139)
        # direction -- "absorbed into scitex-audit", "a deprecated
        # re-export shim of scitex_audit.github", "will be yanked from
        # PyPI at W3" -- and carried archived=True. ADR-0002 (#142,
        # Accepted 2026-06-07 the same afternoon) REVERSED that: security
        # is the unified home; "audit" was the broader codebase but the
        # narrower, more ambiguous name. The reversal was never applied
        # here, so the registry marked the SURVIVOR as archived and the
        # ARCHIVED package as active -- exactly backwards.
        #
        # NOT archived, and NOT to be yanked: scitex-audit is the public
        # archive (2026-07-16 operator ruling), and yanking anything
        # breaks installed callers (ADR-0002).
        "local_path": "~/proj/scitex-security",
        "pypi_name": "scitex-security",
        "github_repo": "scitex-ai/scitex-security",
        "import_name": "scitex_security",
        "category": "library",
    },
    "scitex-session": {
        "local_path": "~/proj/scitex-session",
        "pypi_name": "scitex-session",
        "github_repo": "scitex-ai/scitex-session",
        "import_name": "scitex_session",
        "category": "library",
    },
    "scitex-sh": {
        "local_path": "~/proj/scitex-sh",
        "pypi_name": "scitex-sh",
        "github_repo": "scitex-ai/scitex-sh",
        "import_name": "scitex_sh",
        "category": "library",
    },
    "scitex-tex": {
        "local_path": "~/proj/scitex-tex",
        "pypi_name": "scitex-tex",
        "github_repo": "scitex-ai/scitex-tex",
        "import_name": "scitex_tex",
        "category": "library",
    },
    "scitex-todo": {
        "local_path": "~/proj/scitex-todo",
        "pypi_name": "scitex-todo",
        # Repo renamed + transferred: ywatanabe1989/scitex-todo ->
        # scitex-ai/scitex-cards (gh api full_name, verified
        # 2026-07-21). PyPI name and import name are unchanged.
        "github_repo": "scitex-ai/scitex-cards",
        "import_name": "scitex_todo",
        "category": "library",
    },
    "scitex-web": {
        "local_path": "~/proj/scitex-web",
        "pypi_name": "scitex-web",
        "github_repo": "scitex-ai/scitex-web",
        "import_name": "scitex_web",
        "category": "library",
    },
}


__all__ = ["ECOSYSTEM_PART_2"]


# EOF
