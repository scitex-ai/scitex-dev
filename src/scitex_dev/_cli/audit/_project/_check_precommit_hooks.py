"""PS-HOOK-001 — pre-commit `language: system` hooks must not invoke Python tools.

Reference incident (2026-07, fleet-wide "the pre-commit tests are slow/broken")
--------------------------------------------------------------------------------
figrecipe shipped::

    - id: pytest-testmon
      entry: python -m pytest --testmon
      language: system

`pytest-testmon` was never a declared dependency of figrecipe. `language: system`
means pre-commit runs the entry against **whatever is on the ambient `$PATH`**, so
the hook resolved to a different interpreter on every machine:

* on a clean host  → ``error: unrecognized arguments: --testmon``  (exit 4)
* inside the agent container → ``ModuleNotFoundError: matplotlib`` (exit 4)
* on the ONE machine whose owner had hand-installed testmon → it actually ran

i.e. for almost everyone the hook **never ran a single test — it only blocked the
commit.** Zero `.testmondata` files existed anywhere in the fleet. The gate was
not slow; it was inert, and it failed *closed*.

The same shape, measured on the same day:

* ``davinci-resolve-mcp`` — ``entry: python -m pytest tests/``, ``language:
  system``, ``stages: [pre-commit]``. pytest appears in its pyproject ONLY under
  ``[tool.pytest.ini_options]`` (a CONFIG section, not a dependency). It happened
  to work because pytest was ambient — and took **>14 minutes on every commit**.
* ``pip-project-template`` — a "quick smoke test" hook that inherits
  ``--cov-fail-under=100`` from ``addopts``. The smoke subset covers ~42 % by
  construction, so the hook is **arithmetically incapable of passing**. It was
  copied into every repo seeded from the template.

The defect, precisely
---------------------
**A bare command name under ``language: system`` is a ``$PATH`` lookup.** A
``$PATH`` lookup for a Python tool resolves to whichever virtualenv happens to be
active at commit time, which differs per machine and per shell::

    same repo, same .pre-commit-config.yaml, two machines:
      host      → /home/ywatanabe/.env-3.11/bin/pytest   (py3.11)
      container → /opt/venv-sac/bin/pytest               (py3.12, no repo deps)

Declaring ``pytest`` in ``[project.optional-dependencies].dev`` does NOT fix this:
pre-commit never activates your dev venv. The declaration is a promise about an
environment nobody guaranteed is the one running the hook.

**A gate that is nondeterministic across machines is worse than no gate** — it
blocks honest commits while catching nothing. That is precisely what happened.

What PASSES
-----------
``language: python`` + ``additional_dependencies:`` — pre-commit then builds an
**isolated, cached virtualenv** and installs exactly those deps into it. The
dependency becomes explicit and the resolution becomes hermetic::

    - id: skills-python-tests
      entry: pytest -q skills
      language: python
      additional_dependencies: ["pytest>=8,<9"]

(That is openclaw's hook — the in-fleet exemplar.) Non-Python system tooling
(``bash``, ``grep``, ``pnpm``, ``swiftlint``, or an explicit repo-local path like
``scripts/run-tool.sh``) stays legitimate under ``language: system`` and is never
flagged.

Detection
---------
For every hook with ``language: system``, the entry is unwrapped (``bash -c
'...'`` / ``sh -c '...'``), split on shell operators, and each command's argv[0]
is examined. A violation fires when argv[0] is:

1. a bare ``python`` / ``python3`` / ``python3.N`` — under ``language: system``
   this always means "run Python from whatever venv is ambient"; or
2. a bare, known third-party Python console script (``pytest``, ``mypy``,
   ``ruff``, ``black``, …) — a distribution that only exists on ``$PATH`` if
   somebody pip-installed it into the active environment.

An **explicit path** (anything containing ``/``, e.g. ``./scripts/ci.sh`` or
``.venv/bin/pytest``) is never flagged: a path is a deliberate, repo-controlled
choice, whereas a bare name is the ``$PATH`` lottery.

Opt-out: put ``# PS-HOOK-001: allow`` anywhere in ``.pre-commit-config.yaml``
(intended for the rare genuinely-ambient-safe tool; prefer fixing the hook).

See ``_skills/general/05_development/15_pre-commit-policy.md``.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

try:
    import tomllib  # 3.11+
except ImportError:  # pragma: no cover — 3.10 path
    import tomli as tomllib  # type: ignore[no-redef]


# Console scripts that exist on $PATH only because a Python distribution was
# pip-installed into the *currently active* environment. Under `language:
# system` each of these is a $PATH lottery. Deliberately curated (not "any
# unknown command") so non-Python toolchains — pnpm, swiftlint, oxlint, cargo,
# make — are never touched.
_PYTHON_TOOL_CLIS = frozenset(
    {
        "pytest",
        "py.test",
        "mypy",
        "ruff",
        "black",
        "isort",
        "flake8",
        "pylint",
        "bandit",
        "coverage",
        "pyupgrade",
        "autoflake",
        "autopep8",
        "yapf",
        "docformatter",
        "pydocstyle",
        "codespell",
        "nbstripout",
        "nbqa",
        "vulture",
        "interrogate",
        "pip-audit",
        "safety",
        "tox",
        "nox",
        "twine",
        "sphinx-build",
        "pre-commit",
        # SciTeX's own console scripts have the same ambient-resolution problem.
        "scitex-dev",
        "scitex-todo",
        "scitex-dev-testmon",
    }
)

_PY_INTERPRETER_RE = re.compile(r"^python(?:3(?:\.\d+)?)?$")

# Rule definition, CO-LOCATED with its check.
#
# `_extra_rules.py` (the sidecar that exists because `_registry.py` blew the
# 512-line cap) is now itself over the cap. Rather than grow a third generation
# of sidecar, this rule ships in the shape `_extra_rules.py`'s own docstring
# names as the target architecture: "each rule co-located with its check
# module". `_registry.py` merges HOOK_RULES exactly as it merges EXTRA_RULES.
#
# Severity E (error). The `_SEVERITY_OVERRIDES` doctrine defaults a rule with a
# concrete mechanical spec to E; warn-first is for rules carrying
# false-positive risk. This one was measured against all 16
# `.pre-commit-config.yaml` files in the fleet: it fires on exactly the 6
# known-bad hooks and leaves all 9 legitimate `language: system` hooks alone
# (openclaw's pnpm/oxlint/oxfmt/swiftlint/swiftformat + four bash+grep
# no-debug-code hooks). No scitex-* package has a live `language: system` hook,
# so shipping at E wedges nobody's CI.
#
# (code, section, message, severity, slug)
HOOK_RULES: list[tuple[str, str, str, str, str]] = [
    (
        "PS-HOOK-001",
        "§1",
        (
            "pre-commit hook runs a Python tool (`pytest`, `mypy`, `ruff`, a "
            "bare `python …`, …) under `language: system`. A bare command name "
            "is a $PATH lookup, so the hook resolves to whichever virtualenv "
            "happens to be active at commit time — a different interpreter, "
            "with a different package set, on every machine. Declaring the tool "
            "in `[project.optional-dependencies].dev` does NOT fix this: "
            "pre-commit never activates your dev venv. A gate that is "
            "nondeterministic across machines is worse than no gate — it blocks "
            "honest commits while catching nothing (figrecipe's testmon hook "
            "ran ZERO tests fleet-wide for weeks while blocking every Python "
            "commit; davinci-resolve-mcp's took >14 minutes on every commit). "
            "FIX: use `language: python` + `additional_dependencies: [...]` so "
            "pre-commit builds an isolated venv and the dependency is explicit "
            "(see openclaw's `skills-python-tests` hook); or, if the hook runs "
            "a full test suite, DELETE it and let CI run the tests. An explicit "
            "path (`./scripts/tool.sh`) and non-Python toolchains "
            "(bash/grep/pnpm/swiftlint) are never flagged. Opt-out: "
            "`# PS-HOOK-001: allow` in the config. See "
            "_skills/general/05_development/15_pre-commit-policy.md."
        ),
        "E",
        "precommit-system-hook-ambient-python-tool",
    ),
]

# Shell operators that separate one command from the next. argv[0] of each
# resulting segment is a command position.
_SHELL_OPERATORS = frozenset({"&&", "||", "|", ";", "!", "(", ")", "{", "}"})

_OPTOUT_RE = re.compile(r"#\s*PS-HOOK-001:\s*allow", re.IGNORECASE)


def _unwrap_shell(argv: list[str]) -> list[list[str]]:
    """Expand ``bash -c '<inner>'`` / ``sh -c '<inner>'`` into the inner commands.

    Returns a list of argv lists (command positions). Non-wrapper argv is
    returned as a single-element list.
    """
    if len(argv) >= 3 and Path(argv[0]).name in {"bash", "sh", "zsh"}:
        # find the -c payload
        for i, tok in enumerate(argv[1:], start=1):
            if tok == "-c" and i + 1 < len(argv):
                try:
                    inner = shlex.split(argv[i + 1])
                except ValueError:
                    return [argv]
                return _split_on_operators(inner)
    return [argv]


def _split_on_operators(tokens: list[str]) -> list[list[str]]:
    """Split a token stream into command segments on shell operators."""
    segments: list[list[str]] = []
    current: list[str] = []
    for tok in tokens:
        # A token like "(echo" or "false)" — strip grouping parens so the
        # command name is recoverable.
        stripped = tok.strip("()")
        if tok in _SHELL_OPERATORS or stripped == "":
            if current:
                segments.append(current)
                current = []
            continue
        current.append(stripped)
    if current:
        segments.append(current)
    return segments


def _invoked_python_tool(entry: str) -> str | None:
    """Return the offending Python tool name in ``entry``, or None if clean.

    Only *command positions* are examined — a tool name appearing inside a
    quoted grep pattern or an argument value is never matched.
    """
    try:
        argv = shlex.split(entry)
    except ValueError:
        return None
    if not argv:
        return None

    for segment in _unwrap_shell(argv):
        for cmd_argv in _split_on_operators(segment):
            if not cmd_argv:
                continue
            cmd = cmd_argv[0]
            # Skip leading env-var assignments: FOO=bar pytest ...
            idx = 0
            while (
                idx < len(cmd_argv)
                and "=" in cmd_argv[idx]
                and not cmd_argv[idx].startswith("-")
            ):
                idx += 1
            if idx >= len(cmd_argv):
                continue
            cmd = cmd_argv[idx]

            # An explicit path is a deliberate, repo-controlled choice — not a
            # $PATH lookup. Never flagged.
            if "/" in cmd:
                continue

            if _PY_INTERPRETER_RE.match(cmd):
                rest = cmd_argv[idx + 1 :]
                if len(rest) >= 2 and rest[0] == "-m":
                    return f"{cmd} -m {rest[1]}"
                return cmd
            if cmd in _PYTHON_TOOL_CLIS:
                return cmd
    return None


def _declared_deps(repo: Path) -> tuple[set[str], dict[str, set[str]]]:
    """Return (hard deps, {extra_name: deps}) as normalized distribution names."""
    pp = repo / "pyproject.toml"
    if not pp.is_file():
        return set(), {}
    try:
        meta = tomllib.loads(pp.read_text(encoding="utf-8"))
    except Exception:
        return set(), {}
    project = meta.get("project", {}) or {}

    def _norm(spec: str) -> str:
        name = re.split(r"[<>=!~\s\[;]", spec, maxsplit=1)[0].strip()
        return name.replace("_", "-").lower()

    hard = {_norm(s) for s in (project.get("dependencies") or [])}
    extras = {
        name: {_norm(s) for s in (deps or [])}
        for name, deps in (project.get("optional-dependencies") or {}).items()
    }
    return hard, extras


def _tool_distribution(tool: str) -> str:
    """Map an invoked tool token back to its distribution name for the hint."""
    # "python -m pytest" -> pytest ; "py.test" -> pytest
    token = tool.split()[-1] if " -m " in tool else tool
    return {"py.test": "pytest"}.get(token, token).replace("_", "-").lower()


def _where_declared(
    dist: str, hard: set[str], extras: dict[str, set[str]]
) -> str | None:
    if dist in hard:
        return "[project.dependencies]"
    for extra, deps in extras.items():
        if dist in deps:
            return f"[project.optional-dependencies.{extra}]"
    return None


def check_ps_hook_001_precommit_system_hooks(
    repo: Path, violation_cls: type, out: list
) -> None:
    """Append PS-HOOK-001 violations for ambient-Python `language: system` hooks."""
    cfg = repo / ".pre-commit-config.yaml"
    if not cfg.is_file():
        return
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return
    try:
        raw = cfg.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    if _OPTOUT_RE.search(raw):
        return
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError:
        return
    if not isinstance(data, dict):
        return

    hard, extras = _declared_deps(repo)

    for repo_block in data.get("repos") or []:
        if not isinstance(repo_block, dict):
            continue
        for hook in repo_block.get("hooks") or []:
            if not isinstance(hook, dict):
                continue
            if hook.get("language") != "system":
                continue
            entry = hook.get("entry")
            if not isinstance(entry, str) or not entry.strip():
                continue
            tool = _invoked_python_tool(entry)
            if tool is None:
                continue

            hook_id = hook.get("id", "<unnamed>")
            dist = _tool_distribution(tool)
            declared_at = _where_declared(dist, hard, extras)

            if declared_at is None:
                provenance = (
                    f"`{dist}` is not declared in this repo's dependencies at "
                    f"all — the hook works only by accident, on machines where "
                    f"it happens to be ambient."
                )
            elif declared_at.startswith("[project.optional"):
                provenance = (
                    f"`{dist}` IS declared in `{declared_at}`, but that does "
                    f"NOT put it on the committer's $PATH — pre-commit never "
                    f"activates your dev venv. The declaration promises nothing "
                    f"about the environment that actually runs this hook."
                )
            else:
                provenance = (
                    f"`{dist}` is declared in `{declared_at}`, but "
                    f"`language: system` still resolves it from the ambient "
                    f"$PATH, not from this repo's environment."
                )

            out.append(
                violation_cls(
                    "PS-HOOK-001",
                    f"{cfg}:{hook_id}",
                    (
                        f"hook `{hook_id}` runs `{tool}` under `language: "
                        f"system`. A bare command name is a $PATH lookup, so "
                        f"this resolves to whichever virtualenv is active at "
                        f"commit time — a different interpreter on every "
                        f"machine. {provenance} "
                        f"FIX: switch to `language: python` + "
                        f'`additional_dependencies: ["{dist}"]` so pre-commit '
                        f"builds an isolated venv and the dep is explicit; or, "
                        f"if this is a full test suite, DELETE the hook and let "
                        f"CI run the tests (pre-commit is for fast, bounded, "
                        f"deterministic checks — see "
                        f"_skills/general/05_development/15_pre-commit-policy.md)."
                    ),
                )
            )
