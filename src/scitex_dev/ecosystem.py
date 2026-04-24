#!/usr/bin/env python3
# Timestamp: 2026-02-03
# File: scitex_dev/ecosystem.py

"""SciTeX ecosystem package registry."""

from pathlib import Path
from typing import Dict, List, Optional, TypedDict


class PackageInfo(TypedDict, total=False):
    """Package information structure."""

    local_path: str
    pypi_name: str
    github_repo: str
    import_name: str


# Ordered dict - order matters for display
ECOSYSTEM: Dict[str, PackageInfo] = {
    "scitex": {
        "local_path": "~/proj/scitex-python",
        "pypi_name": "scitex",
        "github_repo": "ywatanabe1989/scitex-python",
        "import_name": "scitex",
    },
    "scitex-io": {
        "local_path": "~/proj/scitex-io",
        "pypi_name": "scitex-io",
        "github_repo": "ywatanabe1989/scitex-io",
        "import_name": "scitex_io",
    },
    "scitex-stats": {
        "local_path": "~/proj/scitex-stats",
        "pypi_name": "scitex-stats",
        "github_repo": "ywatanabe1989/scitex-stats",
        "import_name": "scitex_stats",
    },
    "scitex-clew": {
        "local_path": "~/proj/scitex-clew",
        "pypi_name": "scitex-clew",
        "github_repo": "ywatanabe1989/scitex-clew",
        "import_name": "scitex_clew",
    },
    "scitex-cloud": {
        "local_path": "~/proj/scitex-cloud",
        "pypi_name": "scitex-cloud",
        "github_repo": "ywatanabe1989/scitex-cloud",
        "import_name": "scitex_cloud",
    },
    "figrecipe": {
        "local_path": "~/proj/figrecipe",
        "pypi_name": "figrecipe",
        "github_repo": "ywatanabe1989/figrecipe",
        "import_name": "figrecipe",
    },
    "openalex-local": {
        "local_path": "~/proj/openalex-local",
        "pypi_name": "openalex-local",
        "github_repo": "ywatanabe1989/openalex-local",
        "import_name": "openalex_local",
    },
    "crossref-local": {
        "local_path": "~/proj/crossref-local",
        "pypi_name": "crossref-local",
        "github_repo": "ywatanabe1989/crossref-local",
        "import_name": "crossref_local",
    },
    "scitex-writer": {
        "local_path": "~/proj/scitex-writer",
        "pypi_name": "scitex-writer",
        "github_repo": "ywatanabe1989/scitex-writer",
        "import_name": "scitex_writer",
    },
    "scitex-linter": {
        "local_path": "~/proj/scitex-linter",
        "pypi_name": "scitex-linter",
        "github_repo": "ywatanabe1989/scitex-linter",
        "import_name": "scitex_linter",
    },
    "scitex-dataset": {
        "local_path": "~/proj/scitex-dataset",
        "pypi_name": "scitex-dataset",
        "github_repo": "ywatanabe1989/scitex-dataset",
        "import_name": "scitex_dataset",
    },
    "socialia": {
        "local_path": "~/proj/socialia",
        "pypi_name": "socialia",
        "github_repo": "ywatanabe1989/socialia",
        "import_name": "socialia",
    },
    "automated-research-demo": {
        "local_path": "~/proj/automated-research-demo",
        "pypi_name": "automated-research-demo",
        "github_repo": "ywatanabe1989/automated-research-demo",
        "import_name": "automated_research_demo",
    },
    "scitex-research-template": {
        "local_path": "~/proj/scitex-research-template",
        "pypi_name": "scitex-research-template",
        "github_repo": "ywatanabe1989/scitex-research-template",
        "import_name": "scitex_research_template",
    },
    "pip-project-template": {
        "local_path": "~/proj/pip-project-template",
        "pypi_name": "pip-project-template",
        "github_repo": "ywatanabe1989/pip-project-template",
        "import_name": "pip_project_template",
    },
    "scitex-container": {
        "local_path": "~/proj/scitex-container",
        "pypi_name": "scitex-container",
        "github_repo": "ywatanabe1989/scitex-container",
        "import_name": "scitex_container",
    },
    "scitex-tunnel": {
        "local_path": "~/proj/scitex-tunnel",
        "pypi_name": "scitex-tunnel",
        "github_repo": "ywatanabe1989/scitex-tunnel",
        "import_name": "scitex_tunnel",
    },
    "scitex-ui": {
        "local_path": "~/proj/scitex-ui",
        "pypi_name": "scitex-ui",
        "github_repo": "ywatanabe1989/scitex-ui",
        "import_name": "scitex_ui",
    },
    "scitex-app": {
        "local_path": "~/proj/scitex-app",
        "pypi_name": "scitex-app",
        "github_repo": "ywatanabe1989/scitex-app",
        "import_name": "scitex_app",
    },
    "scitex-audio": {
        "local_path": "~/proj/scitex-audio",
        "pypi_name": "scitex-audio",
        "github_repo": "ywatanabe1989/scitex-audio",
        "import_name": "scitex_audio",
    },
    "scitex-parallel": {
        "local_path": "~/proj/scitex-parallel",
        "pypi_name": "scitex-parallel",
        "github_repo": "ywatanabe1989/scitex-parallel",
        "import_name": "scitex_parallel",
    },
    "scitex-types": {
        "local_path": "~/proj/scitex-types",
        "pypi_name": "scitex-types",
        "github_repo": "ywatanabe1989/scitex-types",
        "import_name": "scitex_types",
    },
    "scitex-path": {
        "local_path": "~/proj/scitex-path",
        "pypi_name": "scitex-path",
        "github_repo": "ywatanabe1989/scitex-path",
        "import_name": "scitex_path",
    },
    "scitex-repro": {
        "local_path": "~/proj/scitex-repro",
        "pypi_name": "scitex-repro",
        "github_repo": "ywatanabe1989/scitex-repro",
        "import_name": "scitex_repro",
    },
    "scitex-compat": {
        "local_path": "~/proj/scitex-compat",
        "pypi_name": "scitex-compat",
        "github_repo": "ywatanabe1989/scitex-compat",
        "import_name": "scitex_compat",
    },
    "scitex-etc": {
        "local_path": "~/proj/scitex-etc",
        "pypi_name": "scitex-etc",
        "github_repo": "ywatanabe1989/scitex-etc",
        "import_name": "scitex_etc",
    },
    "scitex-gists": {
        "local_path": "~/proj/scitex-gists",
        "pypi_name": "scitex-gists",
        "github_repo": "ywatanabe1989/scitex-gists",
        "import_name": "scitex_gists",
    },
    "scitex-audit": {
        "local_path": "~/proj/scitex-audit",
        "pypi_name": "scitex-audit",
        "github_repo": "ywatanabe1989/scitex-audit",
        "import_name": "scitex_audit",
    },
    "scitex-core": {
        "local_path": "~/proj/scitex-core",
        "pypi_name": "scitex-core",
        "github_repo": "ywatanabe1989/scitex-core",
        "import_name": "scitex_core",
    },
    "scitex-db": {
        "local_path": "~/proj/scitex-db",
        "pypi_name": "scitex-db",
        "github_repo": "ywatanabe1989/scitex-db",
        "import_name": "scitex_db",
    },
    "scitex-scholar": {
        "local_path": "~/proj/scitex-scholar",
        "pypi_name": "scitex-scholar",
        "github_repo": "ywatanabe1989/scitex-scholar",
        "import_name": "scitex_scholar",
    },
    "scitex-template": {
        "local_path": "~/proj/scitex-template",
        "pypi_name": "scitex-template",
        "github_repo": "ywatanabe1989/scitex-template",
        "import_name": "scitex_template",
    },
    "scitex-dev": {
        "local_path": "~/proj/scitex-dev",
        "pypi_name": "scitex-dev",
        "github_repo": "ywatanabe1989/scitex-dev",
        "import_name": "scitex_dev",
    },
    "scitex-agent-container": {
        "local_path": "~/proj/scitex-agent-container",
        "pypi_name": "scitex-agent-container",
        "github_repo": "ywatanabe1989/scitex-agent-container",
        "import_name": "scitex_agent_container",
    },
    "scitex-orochi": {
        "local_path": "~/proj/scitex-orochi",
        "pypi_name": "scitex-orochi",
        "github_repo": "ywatanabe1989/scitex-orochi",
        "import_name": "scitex_orochi",
    },
    "singularity-template": {
        "local_path": "~/proj/singularity-template",
        "pypi_name": "singularity-template",
        "github_repo": "ywatanabe1989/singularity-template",
        "import_name": "singularity_template",
    },
    "scitex-str": {
        "local_path": "~/proj/scitex-str",
        "pypi_name": "scitex-str",
        "github_repo": "ywatanabe1989/scitex-str",
        "import_name": "scitex_str",
    },
    "scitex-logging": {
        "local_path": "~/proj/scitex-logging",
        "pypi_name": "scitex-logging",
        "github_repo": "ywatanabe1989/scitex-logging",
        "import_name": "scitex_logging",
    },
    "scitex-dict": {
        "local_path": "~/proj/scitex-dict",
        "pypi_name": "scitex-dict",
        "github_repo": "ywatanabe1989/scitex-dict",
        "import_name": "scitex_dict",
    },
    "scitex-browser": {
        "local_path": "~/proj/scitex-browser",
        "pypi_name": "scitex-browser",
        "github_repo": "ywatanabe1989/scitex-browser",
        "import_name": "scitex_browser",
    },
}


def get_local_path(package: str) -> Optional[Path]:
    """Get expanded local path for a package."""
    if package not in ECOSYSTEM:
        return None
    return Path(ECOSYSTEM[package]["local_path"]).expanduser()


def get_all_packages() -> List[str]:
    """Get list of all ecosystem package names."""
    return list(ECOSYSTEM.keys())


# EOF
