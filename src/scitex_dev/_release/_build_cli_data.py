"""Ship the canonical CLI dictionary without maintaining a second source copy."""

from pathlib import Path

try:
    from setuptools.command.build_py import build_py
except ImportError as exc:
    raise ImportError(
        "This private build hook requires the PEP 517 build dependencies."
    ) from exc


class _BuildCliData(build_py):
    """Copy source-owned audit data into the package's conventional resource."""

    def run(self) -> None:
        """Build modules, then copy the canonical CLI audit dictionary."""
        super().run()
        source = Path(__file__).resolve().parents[3] / ".scitex/dev/cli-audit-dict.yaml"
        target = Path(self.build_lib) / "scitex_dev/_cli_audit_dict.yaml"
        self.copy_file(str(source), str(target))
