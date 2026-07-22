#!/usr/bin/env python3
# Timestamp: 2026-07-23
# File: scitex_dev/_release/entrypoint_imports.py

"""Pre-publish gate: every declared entry point must actually IMPORT.

Bug class caught
----------------

A distribution declares an entry point whose target module is not
importable in the shipped artifact::

    [project.entry-points."pytest11"]
    scitex_dev_test_execution = "scitex_dev._core._test_execution_plugin"

If that module is missing from the wheel — dropped by a packaging rule,
renamed without updating `pyproject.toml`, or moved behind a dependency
that is not installed — nothing fails at BUILD time. The wheel uploads
cleanly, `pip install` succeeds, and the breakage lands in the USER's
tooling instead: an auto-loaded group like `pytest11` is imported by
pytest at startup, so **every** `pytest` invocation in the installed
environment aborts with `ModuleNotFoundError` before collecting a single
test. Console scripts fail the same way on first run.

This module moves that failure back to where it belongs — the build.

Why the INSTALLED distribution, not `pyproject.toml`
---------------------------------------------------

Reading the source tree's declared entry points answers "is the
DECLARATION plausible?" — a review-time question. It cannot catch a
packaging bug, because a declaration can be perfectly correct while the
build drops the file it points at (exactly the failure mode
`pypi_package_data.py` exists for, one level down). So this gate reads
`entry_points.txt` from the BUILT artifact's `.dist-info` and imports
each target with that artifact on `sys.path`. What users install is what
gets probed.

Missing vs. broken
------------------

The two ways an entry point can fail present IDENTICALLY at pytest
startup (both surface as an `ImportError` subclass out of the plugin
loader) and mean completely different things:

- ``missing`` — the target module does not exist in the artifact. A
  PACKAGING or declaration bug: fix the include rules or the
  `pyproject.toml` target.
- ``broken``  — the target module exists and was found, but importing it
  raised. A DEPENDENCY or code bug inside the module: the import chain
  is at fault, not the packaging.

They are classified separately here, and the report says which, because
a bug report that cannot tell them apart sends the fix to the wrong
place.

Isolation
---------

Each probe runs in a SUBPROCESS with the artifact prepended to
`PYTHONPATH` and a neutral working directory, so a half-imported module
cannot poison the auditing process and the repo checkout cannot silently
satisfy an import the artifact would not.

The ambient environment must have the distribution's RUNTIME
DEPENDENCIES installed — the gate asks "does this artifact import where
it will be installed?", not "does it import with no dependencies at
all". The artifact's own modules always win, because its path is
prepended.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# Entry-point groups that are imported AUTOMATICALLY by third-party
# tooling, with no user opt-in. A dangling target in one of these breaks
# the user's tooling at startup rather than on first use, which is why
# this gate exists at all. Reported for prioritisation only — every
# group is probed.
AUTOLOADED_GROUPS = frozenset({"pytest11"})


@dataclass
class EntryPointProbe:
    """Import verdict for one declared entry point."""

    group: str
    name: str
    value: str
    module: str
    attr: str = ""
    status: str = "ok"  # "ok" | "missing" | "broken"
    detail: str = ""

    @property
    def is_autoloaded(self) -> bool:
        """True if third-party tooling imports this group unprompted."""
        return self.group in AUTOLOADED_GROUPS

    def describe(self) -> str:
        """One-line human-readable verdict naming target and cause."""
        head = f"[{self.status.upper()}] {self.group}/{self.name} = {self.value}"
        if self.status == "ok":
            return head
        if self.is_autoloaded:
            head += " (AUTO-LOADED group — breaks tooling at startup)"
        return f"{head}\n    {self.detail}"


@dataclass
class EntryPointAuditReport:
    """Result of importing every entry point a distribution declares."""

    distribution_name: str
    distribution_version: str = ""
    metadata_path: Path | None = None
    probes: list[EntryPointProbe] = field(default_factory=list)

    @property
    def failures(self) -> list[EntryPointProbe]:
        """Probes whose target did not import."""
        return [p for p in self.probes if p.status != "ok"]

    @property
    def missing(self) -> list[EntryPointProbe]:
        """Probes whose target module does not exist (packaging bug)."""
        return [p for p in self.probes if p.status == "missing"]

    @property
    def broken(self) -> list[EntryPointProbe]:
        """Probes whose target exists but raised on import (dep/code bug)."""
        return [p for p in self.probes if p.status == "broken"]

    @property
    def is_clean(self) -> bool:
        """True if every declared entry point imported.

        A distribution declaring NO entry points is clean: there is
        nothing that can dangle. This is deliberate — a gate that
        flagged the empty case would be flagging everything.
        """
        return not self.failures

    def summary(self) -> str:
        """One-line summary."""
        if self.is_clean:
            return (
                f"{self.distribution_name}: ok "
                f"({len(self.probes)} entry points import)"
            )
        return (
            f"{self.distribution_name}: "
            f"{len(self.failures)}/{len(self.probes)} entry points FAIL to "
            f"import ({len(self.missing)} missing target, "
            f"{len(self.broken)} broken import)"
        )

    def report(self) -> str:
        """Full multi-line report: summary plus every failing probe."""
        lines = [self.summary()]
        lines.extend(p.describe() for p in self.failures)
        return "\n".join(lines)


# Probe body, executed in a subprocess. Prints one JSON list on stdout.
#
# Classification rule for a raised ModuleNotFoundError: if the module it
# names is the target itself or one of the target's PARENT packages, the
# target genuinely is not present -> "missing". Anything else — including
# a ModuleNotFoundError for some unrelated module imported INSIDE the
# target — means the target was found and its own import chain failed
# -> "broken". Without this distinction an internal `import
# some_absent_dep` would be misreported as a packaging bug.
_PROBE_SRC = r'''
import importlib
import importlib.util
import json
import sys
import traceback


def _names_target(exc, target):
    name = getattr(exc, "name", None)
    if not name:
        return False
    return target == name or target.startswith(name + ".")


def _probe(target, attr):
    try:
        spec = importlib.util.find_spec(target)
    except ModuleNotFoundError as exc:
        if _names_target(exc, target):
            return "missing", "no module named %r in this distribution" % (
                getattr(exc, "name", target),
            )
        return "broken", "".join(traceback.format_exception_only(type(exc), exc)).strip()
    except Exception as exc:
        return "broken", "".join(traceback.format_exception_only(type(exc), exc)).strip()
    if spec is None:
        return "missing", "no module named %r in this distribution" % (target,)
    try:
        mod = importlib.import_module(target)
    except Exception as exc:
        return "broken", "".join(traceback.format_exception_only(type(exc), exc)).strip()
    if attr:
        obj = mod
        for part in attr.split("."):
            if not hasattr(obj, part):
                return "broken", (
                    "module imported but declared attribute %r is not defined "
                    "in it" % (attr,)
                )
            obj = getattr(obj, part)
    return "ok", str(getattr(spec, "origin", "") or "")


targets = json.loads(sys.argv[1])
out = []
for target, attr in targets:
    status, detail = _probe(target, attr)
    out.append({"target": target, "attr": attr, "status": status, "detail": detail})
sys.stdout.write(json.dumps(out))
'''


def _split_value(value: str) -> tuple[str, str]:
    """Split an entry-point value into ``(module, attr)``."""
    module, sep, attr = value.partition(":")
    return module.strip(), (attr.strip() if sep else "")


def _find_distribution(dist_name: str, search_paths: list[Path] | None):
    """Return the `importlib.metadata.Distribution` for `dist_name`.

    When `search_paths` is given, ONLY those paths are searched — so the
    artifact's own `entry_points.txt` is read, never an ambient install's.
    """
    from importlib.metadata import Distribution, distributions
    from packaging.utils import canonicalize_name

    if search_paths is None:
        return Distribution.from_name(dist_name)

    wanted = canonicalize_name(dist_name)
    for dist in distributions(path=[str(p) for p in search_paths]):
        raw = dist.metadata["Name"] if dist.metadata else None
        if raw and canonicalize_name(raw) == wanted:
            return dist
    raise LookupError(
        f"no installed distribution named {dist_name!r} under "
        f"{[str(p) for p in search_paths]} — the artifact carries no "
        f"`.dist-info` for it, so its entry points cannot be audited"
    )


def audit_entry_point_imports(
    dist_name: str,
    *,
    search_paths: list[Path] | None = None,
    python: str | None = None,
    timeout: int = 300,
) -> EntryPointAuditReport:
    """Import every entry point `dist_name` declares; report failures.

    Parameters
    ----------
    dist_name : str
        Distribution name, e.g. ``scitex-dev``.
    search_paths : list[Path] | None
        Directories holding the distribution to audit (an unpacked wheel,
        a `--target` install). Metadata is read ONLY from here, and these
        paths are PREPENDED to the probe's `PYTHONPATH` so the artifact's
        modules win over any ambient install. `None` audits the ambient
        environment's installed distribution.
    python : str | None
        Interpreter used for the probe subprocess. Default: `sys.executable`.
    timeout : int
        Seconds allowed for the probe subprocess.

    Returns
    -------
    EntryPointAuditReport
    """
    import os

    dist = _find_distribution(dist_name, search_paths)
    eps = list(dist.entry_points)

    probes = [
        EntryPointProbe(
            group=ep.group,
            name=ep.name,
            value=ep.value,
            module=_split_value(ep.value)[0],
            attr=_split_value(ep.value)[1],
        )
        for ep in eps
    ]
    probes.sort(key=lambda p: (p.group, p.name))

    version = ""
    try:
        version = dist.version
    except Exception:
        version = ""
    meta_path = getattr(dist, "_path", None)

    report = EntryPointAuditReport(
        distribution_name=dist_name,
        distribution_version=version,
        metadata_path=Path(meta_path) if meta_path else None,
        probes=probes,
    )
    # Control case: nothing declared, nothing can dangle. Do not spawn a
    # probe just to prove an empty list is empty.
    if not probes:
        return report

    env = dict(os.environ)
    if search_paths:
        prefix = os.pathsep.join(str(p) for p in search_paths)
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            prefix + os.pathsep + existing if existing else prefix
        )

    payload = json.dumps([[p.module, p.attr] for p in probes])
    with tempfile.TemporaryDirectory(prefix="scitex-ep-audit-") as neutral_cwd:
        proc = subprocess.run(
            [python or sys.executable, "-c", _PROBE_SRC, payload],
            cwd=neutral_cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    if proc.returncode != 0:
        raise RuntimeError(
            "entry-point probe subprocess failed "
            f"(exit {proc.returncode}):\n{proc.stderr}"
        )
    try:
        results = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"entry-point probe produced unparseable output: {exc}\n"
            f"stdout: {proc.stdout!r}\nstderr: {proc.stderr!r}"
        ) from exc

    by_target = {(r["target"], r["attr"]): r for r in results}
    for probe in probes:
        result = by_target.get((probe.module, probe.attr))
        if result is None:
            probe.status = "broken"
            probe.detail = "probe returned no verdict for this target"
            continue
        probe.status = result["status"]
        if probe.status == "missing":
            probe.detail = (
                f"target module `{probe.module}` DOES NOT EXIST "
                f"({result['detail']}). This is a PACKAGING or declaration "
                "bug: either the module was dropped from the built artifact, "
                "or the entry-point target in pyproject.toml names a module "
                "that was renamed or removed."
            )
        elif probe.status == "broken":
            probe.detail = (
                f"target module `{probe.module}` EXISTS but FAILED to import: "
                f"{result['detail']}. This is NOT a missing module — the "
                "packaging is fine and the target was found. The fault is "
                "inside the module's own import chain (a missing dependency "
                "or an error at module scope)."
            )
    return report


def unpack_wheel(wheel_path: Path, dest: Path) -> Path:
    """Extract `wheel_path` into `dest`; return `dest`.

    A wheel is a zip whose members are already laid out exactly as an
    installed distribution (package dirs plus `*.dist-info/`), so
    extraction alone yields something `importlib.metadata` and `sys.path`
    both understand — no `pip`, no network, no venv.
    """
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(wheel_path) as zf:
        zf.extractall(dest)
    return dest


def audit_wheel_entry_point_imports(
    wheel_path: Path,
    dist_name: str,
    *,
    python: str | None = None,
) -> EntryPointAuditReport:
    """Import every entry point declared by a BUILT WHEEL.

    Unpacks the wheel to a temp dir and audits it there, so the verdict
    is about the artifact users will install — not about the source
    checkout that produced it.
    """
    wheel_path = Path(wheel_path)
    if not wheel_path.is_file():
        raise FileNotFoundError(f"no wheel at {wheel_path}")
    with tempfile.TemporaryDirectory(prefix="scitex-ep-wheel-") as tmp:
        root = unpack_wheel(wheel_path, Path(tmp) / "unpacked")
        return audit_entry_point_imports(
            dist_name, search_paths=[root], python=python
        )


# EOF
