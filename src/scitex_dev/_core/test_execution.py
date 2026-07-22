#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: scitex_dev/_core/test_execution.py

"""Per-package test-execution policy — a host/scheduler-AGNOSTIC recipe.

A package may declare *where* its test-suite is allowed to run. The policy is
a small YAML **recipe** stored in the canonical config-layout
(``~/.scitex/<pkg-short>/test-execution.yaml`` — tracked, resolved via
``scitex_config._ecosystem.local_state``), self-describing enough that a
pytest guard, the ``ecosystem test-remote`` command, and the scitex-dev knob
all read the same file.

Two modes:

* ``local`` (default) — local pytest is fine; the guard is inert.
* ``remote-required`` — running pytest locally is an ERROR. The suite must be
  submitted to a remote/compute node. The recipe names that node
  (``remote_host``) and a **submit-command template** (``submit_template``)
  with ``{placeholder}`` slots filled from the free-form ``params`` map plus
  the special ``{pytest_args}`` / ``{host}`` slots.

The mechanism hardcodes NO cluster, scheduler, partition, or command. Spartan
+ ``srun`` is only ONE instance a user configures, e.g.::

    mode: remote-required
    remote_host: spartan-bm198
    submit_template: "srun -p {partition} -c {cpus} --time={time} pytest -n {cpus} {pytest_args}"
    local_marker_env: SCITEX_TEST_ON_REMOTE
    params:
      partition: gpu-a100
      cpus: 16
      time: "00:30:00"

(Note the explicit ``-n {cpus}`` rather than ``-n auto``: see
``allocated_cpus`` for why ``auto`` over-subscribes a Slurm allocation.)

Another user points ``remote_host`` at their own box and writes their own
``submit_template`` (``qsub``, ``sbatch``, a bare ``ssh`` — anything) and the
same code path works unchanged.

The ``local_marker_env`` names an environment variable whose presence means
"I am already ON the sanctioned remote/compute node, so allow local pytest."
The remote invocation (``ecosystem test-remote``) exports it, so the guard
never fires there — and it stays inert by default because the default mode is
``local``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from scitex_config._ecosystem import local_state

TEST_EXECUTION_MODES = ("local", "remote-required")
DEFAULT_MODE = "local"
DEFAULT_MARKER_ENV = "SCITEX_TEST_ON_REMOTE"
RECIPE_FILENAME = "test-execution.yaml"
# Env var pointing directly at a recipe YAML (overrides layout discovery).
RECIPE_PATH_ENV = "SCITEX_TEST_EXECUTION_RECIPE"

_KNOWN_KEYS = frozenset(
    {"mode", "remote_host", "submit_template", "local_marker_env", "params", "extra"}
)


@dataclass(frozen=True)
class TestExecutionConfig:
    """A parsed, immutable test-execution recipe.

    ``params`` is a free-form map (partition / time / account / ...) whose keys
    become ``{placeholder}`` values when rendering ``submit_template``.
    """

    # Not a pytest test class despite the "Test" prefix — tell the collector.
    __test__ = False

    mode: str = DEFAULT_MODE
    remote_host: str | None = None
    submit_template: str | None = None
    local_marker_env: str = DEFAULT_MARKER_ENV
    params: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode not in TEST_EXECUTION_MODES:
            raise ValueError(
                f"mode must be one of {TEST_EXECUTION_MODES}, got {self.mode!r}"
            )

    @property
    def is_remote_required(self) -> bool:
        return self.mode == "remote-required"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "remote_host": self.remote_host,
            "submit_template": self.submit_template,
            "local_marker_env": self.local_marker_env,
            "params": dict(self.params),
        }


def _pkg_short(pkg: str) -> str:
    """Map an ecosystem package name to its config-layout short name.

    ``scitex-hpc`` → ``hpc``; a bare name (``figrecipe``) is returned as-is.
    Mirrors the layout convention used across the SciTeX ``~/.scitex/<short>/``
    tree.
    """
    return pkg[len("scitex-") :] if pkg.startswith("scitex-") else pkg


def recipe_path(pkg: str, *, path: str | Path | None = None) -> Path:
    """Resolve the recipe YAML path for ``pkg``.

    Explicit ``path`` wins; otherwise the tracked config-layout location
    ``local_state.path(<pkg-short>, "test-execution.yaml")`` is returned
    (whether or not it exists — the loader tolerates absence).
    """
    if path is not None:
        return Path(path).expanduser()
    return local_state.path(_pkg_short(pkg), RECIPE_FILENAME)


def _from_mapping(data: Mapping[str, Any] | None) -> TestExecutionConfig:
    """Build a recipe from a parsed YAML mapping (empty/None → default)."""
    if not data:
        return TestExecutionConfig()
    params: dict[str, Any] = {}
    # Explicit params/extra map, then any unknown top-level keys, so a user can
    # write placeholders flat (``partition: gpu``) or nested (``params: {...}``).
    for container_key in ("params", "extra"):
        block = data.get(container_key)
        if isinstance(block, Mapping):
            params.update(block)
    for key, value in data.items():
        if key not in _KNOWN_KEYS:
            params[key] = value
    return TestExecutionConfig(
        mode=str(data.get("mode", DEFAULT_MODE)),
        remote_host=data.get("remote_host"),
        submit_template=data.get("submit_template"),
        local_marker_env=str(data.get("local_marker_env", DEFAULT_MARKER_ENV)),
        params=params,
    )


def load_recipe(path: str | Path | None) -> TestExecutionConfig:
    """Load a recipe from a YAML file; a missing/empty file → default (local).

    FAILS SAFE: this is called by an auto-loaded pytest plugin in every
    environment where scitex-dev is installed, so a malformed YAML, an
    unreadable file, or an invalid ``mode`` value must NEVER crash pytest.
    Any error is downgraded to a warning and the inert default (mode=local)
    is returned — a broken recipe disables the guard, it does not brick the
    test run.
    """
    if path is None:
        return TestExecutionConfig()
    p = Path(path).expanduser()
    if not p.exists():
        return TestExecutionConfig()
    try:
        import yaml

        data = yaml.safe_load(p.read_text()) or {}
        if not isinstance(data, Mapping):
            return TestExecutionConfig()
        return _from_mapping(data)
    except Exception as exc:  # noqa: BLE001 — fail-safe guard, never break pytest
        import warnings

        warnings.warn(
            f"scitex-dev: ignoring unreadable test-execution recipe {p} "
            f"({type(exc).__name__}: {exc}); defaulting to mode=local.",
            stacklevel=2,
        )
        return TestExecutionConfig()


def load_test_execution(
    pkg: str, *, path: str | Path | None = None
) -> TestExecutionConfig:
    """Resolve + load the recipe for ``pkg`` from the config-layout."""
    return load_recipe(recipe_path(pkg, path=path))


def allocated_cpus(environ: Mapping[str, str] | None = None) -> int:
    """CPUs THIS process is actually allowed to use — never the machine's total.

    The xdist-worker-count policy (ADR-0004 P1(b)). ``pytest -n auto`` cannot
    be trusted to answer this: pytest-xdist's ``pytest_xdist_auto_num_workers``
    consults **psutil first** and returns its count immediately if it gets one
    (``xdist/plugin.py`` 3.8.0, lines 26-34) — and ``psutil.cpu_count()`` reads
    the machine, ignoring cgroup/cpuset confinement. Only if psutil is absent
    does xdist fall through to ``sched_getaffinity``, which IS correct.

    Measured on the Spartan CI runner node (spartan-bm155, inside the
    48-CPU lease cgroup ``job_27144058/step_extern``)::

        os.sched_getaffinity(0)          48   <- the allocation
        os.cpu_count()                  128
        psutil.cpu_count(logical=False)  128   <- what `-n auto` used
        psutil.cpu_count()              128

    i.e. `-n auto` spawned ~128 workers into a 48-CPU allocation (observed as
    worker ids reaching ``gw121``), a 2.7x continuous oversubscription.

    Resolution order:

      1. ``SLURM_CPUS_PER_TASK`` — set inside an ``srun``/``sbatch`` step.
      2. ``SLURM_JOB_CPUS_PER_NODE`` — the batch allocation's per-node count
         (leading integer; the ``"48(x2)"`` form is truncated to ``48``).
      3. ``os.sched_getaffinity(0)`` — authoritative under a cgroup cpuset,
         and the ONLY one of these present on the CI runner: the runner is
         reached by ssh and adopted into the lease cgroup, so it inherits the
         cpuset but NOT the step's Slurm environment variables (both SLURM_*
         vars above measured EMPTY there).
      4. ``os.cpu_count()`` — a developer laptop with no allocation at all.

    No magic cap and no hardcoded core count: an unconstrained machine still
    gets all of its cores, which is what a laptop or a dedicated box wants.
    """
    env = os.environ if environ is None else environ
    for var in ("SLURM_CPUS_PER_TASK", "SLURM_JOB_CPUS_PER_NODE"):
        raw = (env.get(var) or "").strip()
        # "48(x2)" / "48,32" — the leading integer is this node's count.
        leading = ""
        for ch in raw:
            if not ch.isdigit():
                break
            leading += ch
        if leading:
            n = int(leading)
            if n > 0:
                return n
    getaffinity = getattr(os, "sched_getaffinity", None)
    if getaffinity is not None:
        try:
            n = len(getaffinity(0))
            if n > 0:
                return n
        except OSError:  # pragma: no cover - platform-dependent
            pass
    return max(1, os.cpu_count() or 1)


# The same policy as `allocated_cpus`, as a one-line `python -c` snippet, for
# invocations that must resolve the count ON A REMOTE HOST (the local box's
# allocation is irrelevant and would be wrong). Kept beside the Python
# implementation so the two cannot drift apart unnoticed.
ALLOCATED_CPUS_PY_SNIPPET = (
    "import os; "
    '_vars = ("SLURM_CPUS_PER_TASK", "SLURM_JOB_CPUS_PER_NODE"); '
    '_raw = next((v for v in (os.environ.get(k, "").strip() for k in _vars) '
    "if v[:1].isdigit()), \"\"); "
    '_n = int(_raw.split(",")[0].split("(")[0]) if _raw else 0; '
    "_aff = len(os.sched_getaffinity(0)) "
    'if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1); '
    "print(max(1, _n or _aff))"
)


# The env var pytest-xdist consults BEFORE psutil (xdist/plugin.py:17-24), so
# setting it makes an unmodified `-n auto` resolve to the allocation.
XDIST_AUTO_WORKERS_ENV = "PYTEST_XDIST_AUTO_NUM_WORKERS"


class _SafeDict(dict):
    """format_map helper: leave unknown ``{placeholders}`` literally intact."""

    def __missing__(self, key: str) -> str:  # pragma: no cover - trivial
        return "{" + key + "}"


def render_submit(recipe: TestExecutionConfig, pytest_args: str) -> str:
    """Render ``submit_template`` with recipe params + ``{pytest_args}``/``{host}``.

    Raises ``ValueError`` if the recipe carries no ``submit_template``.
    Unknown placeholders are left literal so a misconfigured template is
    visible rather than silently dropped.
    """
    if not recipe.submit_template:
        raise ValueError("recipe has no submit_template to render")
    values = _SafeDict(recipe.params)
    values["pytest_args"] = pytest_args
    values["host"] = recipe.remote_host or ""
    return recipe.submit_template.format_map(values)


def is_on_sanctioned_remote(
    recipe: TestExecutionConfig, environ: Mapping[str, str] | None = None
) -> bool:
    """True iff the marker env var is set (non-empty) — i.e. we ARE on remote."""
    env = os.environ if environ is None else environ
    return bool(env.get(recipe.local_marker_env, ""))


def guard_message(
    recipe: TestExecutionConfig, environ: Mapping[str, str] | None = None
) -> str | None:
    """Return an actionable block message, or ``None`` when local pytest is OK.

    Blocks only when ``mode == "remote-required"`` AND we are not on the
    sanctioned remote (marker env unset). Mode ``local`` always returns
    ``None`` — the guard is inert by default.
    """
    if not recipe.is_remote_required:
        return None
    if is_on_sanctioned_remote(recipe, environ):
        return None
    host = recipe.remote_host or "the configured remote host"
    return (
        "This package mandates REMOTE test execution "
        "(test-execution.yaml: mode=remote-required).\n"
        "Local pytest is disabled to avoid overloading this machine.\n"
        f"Run the suite on {host} instead, e.g.:\n"
        "    scitex-dev ecosystem test-remote --host "
        f"{recipe.remote_host or '<host>'} <package>\n"
        f"(Set {recipe.local_marker_env}=1 only when you are genuinely ON the "
        "sanctioned remote/compute node.)"
    )


def discover_recipe(
    start: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> TestExecutionConfig:
    """Find the recipe governing tests rooted at ``start`` (default cwd).

    Resolution order:
      1. ``$SCITEX_TEST_EXECUTION_RECIPE`` — explicit recipe path.
      2. A ``.scitex/*/test-execution.yaml`` under the enclosing git repo root
         (the package's own tracked config-layout).
      3. Default (mode=local) — nothing found, guard inert.

    No package name is needed, so this works for the pytest plugin which only
    knows the checkout it is running in.
    """
    env = os.environ if environ is None else environ
    explicit = env.get(RECIPE_PATH_ENV)
    if explicit:
        return load_recipe(explicit)
    # Fail SAFE around filesystem discovery too (cwd may be gone, globs may
    # error): a discovery failure must never crash the pytest run — default
    # to the inert local mode. `load_recipe` handles its own parse errors.
    try:
        here = Path(start).resolve() if start is not None else Path.cwd().resolve()
        for candidate in [here, *here.parents]:
            if (candidate / ".git").exists():
                matches = sorted((candidate / ".scitex").glob(f"*/{RECIPE_FILENAME}"))
                if matches:
                    return load_recipe(matches[0])
                break
    except Exception:  # noqa: BLE001 — fail-safe guard, never break pytest
        return TestExecutionConfig()
    return TestExecutionConfig()


# EOF
