"""Skill trigger-rate testing (Layer 2).

Given a clean Claude instance and only a skill index, does the expected
SKILL.md get viewed when the user asks a realistic question? Trigger-rate
testing answers that, without any API spend: we shell out to `claude -p`
(Claude Code non-interactive mode), parse the JSON transcript, and check
which files the agent chose to `view`/`Read`.

Two runner backends share a single ``ClaudeRunner`` protocol:

- ``HostRunner`` — shells out to the host-installed ``claude`` CLI. Rotates
  across Claude Code HOME dirs (each is a logged-in account), skipping
  quota-exceeded accounts for the rest of the session. Free (plan quota)
  but inherits any host-side cache and installed skills.
- ``NewbieDockerRunner`` — shells out to ``docker exec`` inside a
  long-lived ``scitex-agent-container:latest`` container configured like
  the ``newbie-docker`` template (network=bridge, no ~/.claude mount).
  Uses ``ANTHROPIC_API_KEY`` billing but gives a clean-slate agent per
  session. Empirically 2-6× cheaper per call than host on a Haiku
  "hello" (cache_creation=0-5K vs ~12K on host) — see the
  16_skill-trigger-testing skill leaf for the measurement table.

Select backend at call site or via env:

    SCITEX_DEV_AGENTIC_BACKEND=host   (default)
    SCITEX_DEV_AGENTIC_BACKEND=docker

Reference JSON shape (verified 2026-04-23 with claude-haiku-4-5):

    {"type": "result", "subtype": "success", "is_error": false,
     "result": "<final assistant text>",
     "session_id": "...", "usage": {...}, "modelUsage": {...},
     "iterations": [ ... per-turn records ... ],
     ...}

``extract_viewed_paths`` walks the entire payload recursively so it is
tolerant to the exact top-level envelope.
"""

from __future__ import annotations

import atexit
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

DEFAULT_ACCOUNTS = [
    # Each entry is a HOME directory (not the .claude config dir).
    # Claude Code reads auth from $HOME/.claude/, so HOME must be the
    # parent of .claude, not .claude itself. Empirically verified
    # 2026-04-23 — pointing at ~/.claude yielded "Not logged in".
    # Override via SCITEX_DEV_CLAUDE_ACCOUNTS env (":"-separated HOME paths).
    Path.home(),
]
DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_TIMEOUT = 120
RUNS_PER_CASE = 3

# Published from scitex-agent-container's publish-agentic-test-image.yml
# workflow on every v* tag (and via workflow_dispatch). See
# scitex-agent-container/containers/Dockerfile.agentic-test for the source.
DEFAULT_DOCKER_IMAGE = "ghcr.io/ywatanabe1989/scitex-agentic-test:latest"


@dataclass
class EvalCase:
    id: str
    query: str
    expected_skill: str | None  # None = negative test (no skill should be viewed)
    complexity: str = "high"
    # Soft-trigger detection: substrings that should appear in the answer
    # when the skill body was consulted (via explicit Read OR via
    # Claude Code's description-match auto-load). Pick skill-specific
    # strings unlikely to come from model training alone.
    answer_contains: list[str] | None = None


@dataclass
class TriggerResult:
    case: EvalCase
    runs: list[bool]  # pass/fail per run (hard OR soft)
    viewed_paths_per_run: list[list[str]]
    answers_per_run: list[str] = field(default_factory=list)
    hard_trigger_per_run: list[bool] = field(default_factory=list)
    soft_trigger_per_run: list[bool] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return sum(self.runs) / len(self.runs)

    @property
    def passed(self) -> bool:
        return sum(self.runs) >= 2  # 2-of-3

    @property
    def hard_pass_rate(self) -> float:
        if not self.hard_trigger_per_run:
            return 0.0
        return sum(self.hard_trigger_per_run) / len(self.hard_trigger_per_run)

    @property
    def soft_pass_rate(self) -> float:
        if not self.soft_trigger_per_run:
            return 0.0
        return sum(self.soft_trigger_per_run) / len(self.soft_trigger_per_run)


class ClaudeRunner(Protocol):
    """Shared interface for host-side and docker-side `claude -p` runners."""

    def run(
        self,
        prompt: str,
        *,
        model: str = DEFAULT_MODEL,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> dict: ...

    def close(self) -> None: ...


class HostRunner:
    """Round-robin across Claude Code HOME dirs with quota-exceeded skip.

    This is the original ``ClaudeCodePool`` behaviour, preserved verbatim
    and renamed to fit the ``ClaudeRunner`` protocol.
    """

    def __init__(self, accounts: list[Path] | None = None):
        env = os.environ.get("SCITEX_DEV_CLAUDE_ACCOUNTS")
        self.accounts = (
            [Path(p).expanduser() for p in env.split(":")]
            if env
            else accounts or DEFAULT_ACCOUNTS
        )
        self._idx = 0
        self._exceeded: set[Path] = set()

    def _next(self) -> Path:
        for _ in range(len(self.accounts)):
            acc = self.accounts[self._idx]
            self._idx = (self._idx + 1) % len(self.accounts)
            if acc not in self._exceeded:
                return acc
        raise RuntimeError("All Claude Code accounts have exceeded quota")

    def run(
        self,
        prompt: str,
        *,
        model: str = DEFAULT_MODEL,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> dict:
        acc = self._next()
        env = {**os.environ, "HOME": str(acc)}
        proc = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json", "--model", model],
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
        # crude quota detection — refine after first real failure
        if proc.returncode != 0 and any(
            kw in (proc.stderr + proc.stdout).lower()
            for kw in ("quota", "rate limit", "usage limit")
        ):
            self._exceeded.add(acc)
            return self.run(prompt, model=model, timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"claude -p failed: {proc.stderr[:500]}")
        return json.loads(proc.stdout)

    def close(self) -> None:  # no-op for host
        return None


# Backward-compat alias — external code may still import `ClaudeCodePool`.
ClaudeCodePool = HostRunner


class NewbieDockerRunner:
    """Run ``claude -p`` inside a long-lived newbie-docker container.

    Empirically validated 2026-04-23:
        - network=bridge + mount_host_claude=false (clean slate)
        - 2.3-3.3 s / call on Haiku (matches host)
        - $0.003-$0.010 per "hello" (2-6× cheaper than host's ~$0.018)
        - cache_creation_input_tokens 0-5K (vs ~12K on host)

    A single container is reused across all calls for this process. Named
    ``scitex-agentic-test-<pid>`` and torn down via ``close()``; also
    registered with ``atexit`` so tests that crash still clean up.
    """

    def __init__(
        self,
        image: str | None = None,
        *,
        api_key_env: str = "SCITEX_AGENT_CONTAINER_CI_ANTHROPIC_API_KEY",
        skills_mount: Path | None = None,
        system_prompt: str | None = None,
    ):
        self.image = (
            image
            or os.environ.get("SCITEX_DEV_AGENTIC_DOCKER_IMAGE")
            or DEFAULT_DOCKER_IMAGE
        )
        self.container_name = f"scitex-agentic-test-{os.getpid()}"
        self._started = False
        # Optional read-only HOME mount (must contain ``.claude/skills/...``)
        # mounted at ``/home/agent/.claude`` so `claude` sees a scoped skill
        # catalog without any auth/projects baggage from the host.
        self.skills_mount = Path(skills_mount).resolve() if skills_mount else None
        # Optional system prompt appended to every ``run()``. ``claude`` CLI
        # supports ``--system-prompt``; if the installed version rejects it,
        # we fall back silently (see ``run()``).
        self.system_prompt = system_prompt
        self._system_prompt_unsupported = False

        # Verify docker is available up-front.
        try:
            subprocess.run(
                ["docker", "version"],
                capture_output=True,
                check=True,
                timeout=10,
            )
        except FileNotFoundError as e:
            raise RuntimeError(
                "NewbieDockerRunner requires `docker` on PATH. "
                "Install Docker or set SCITEX_DEV_AGENTIC_BACKEND=host."
            ) from e
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"`docker version` failed — daemon not running? stderr="
                f"{e.stderr.decode(errors='replace')[:200]}"
            ) from e

        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(
                f"NewbieDockerRunner needs ${api_key_env} set "
                f"(used as ANTHROPIC_API_KEY inside the container)."
            )
        self._api_key = api_key
        atexit.register(self.close)

    def _start(self) -> None:
        if self._started:
            return
        # Remove any stale container with the same name (previous crashed run).
        subprocess.run(
            ["docker", "rm", "-f", self.container_name],
            capture_output=True,
            check=False,
        )
        # Launch long-lived container: sleep infinity + clean env.
        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            self.container_name,
            "--network",
            "bridge",
            "-e",
            "CLAUDE_DISABLE_AUTO_UPDATE=1",
            "-e",
            f"ANTHROPIC_API_KEY={self._api_key}",
            "-e",
            "HOME=/home/agent",
        ]
        if self.skills_mount is not None:
            # Mount the scoped ``.claude`` tree read-only at the agent HOME so
            # ``claude`` picks up ``$HOME/.claude/skills/scitex/...`` and
            # nothing else (no prior projects, no auth config).
            cmd += [
                "-v",
                f"{self.skills_mount}/.claude:/home/agent/.claude:ro",
            ]
        cmd += [
            "--entrypoint",
            "sleep",
            self.image,
            "infinity",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            # Image likely not pulled yet — try once before giving up. Costs
            # one network round-trip on first invocation per host; fast on the
            # subsequent calls. Stays silent (no echo) so test output is clean.
            stderr = proc.stderr or ""
            if (
                "Unable to find image" in stderr
                or "manifest unknown" in stderr
                or "pull" in stderr.lower()
            ):
                pull = subprocess.run(
                    ["docker", "pull", self.image],
                    capture_output=True,
                    text=True,
                )
                if pull.returncode == 0:
                    proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(
                    f"docker run failed for image {self.image!r}: {proc.stderr[:500]}"
                )
        self._started = True

    def run(
        self,
        prompt: str,
        *,
        model: str = DEFAULT_MODEL,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> dict:
        self._start()

        def _build_cmd(with_system_prompt: bool) -> list[str]:
            c = [
                "docker",
                "exec",
                "-u",
                "agent",
                "-e",
                "HOME=/home/agent",
                self.container_name,
                "claude",
                "-p",
                prompt,
                # stream-json + verbose surfaces intermediate ``tool_use``
                # blocks (Skill, view, Read, Bash, ...) so the caller can see
                # which skills/files the agent actually consulted. The plain
                # ``json`` format only returns the final envelope with no
                # tool-use trace.
                "--output-format",
                "stream-json",
                "--verbose",
                "--model",
                model,
            ]
            if (
                with_system_prompt
                and self.system_prompt
                and not self._system_prompt_unsupported
            ):
                # ``--append-system-prompt`` keeps the default Claude Code
                # system prompt (incl. skill-discovery machinery) and appends
                # our nudge. Using ``--system-prompt`` would replace the whole
                # system prompt and disable skill auto-discovery — verified
                # empirically 2026-04-23 (runs showed ``viewed=[]`` for every
                # case).
                c += ["--append-system-prompt", self.system_prompt]
            return c

        def _one(with_sp: bool) -> subprocess.CompletedProcess:
            return subprocess.run(
                _build_cmd(with_sp),
                capture_output=True,
                text=True,
                timeout=timeout,
            )

        proc = _one(with_sp=True)
        # If --system-prompt isn't supported by this claude version, note it
        # and retry without the flag (silent fallback per spec).
        if (
            proc.returncode != 0
            and self.system_prompt
            and not self._system_prompt_unsupported
            and (
                "unknown option" in (proc.stderr + proc.stdout).lower()
                or "--system-prompt" in (proc.stderr + proc.stdout).lower()
                and "error" in (proc.stderr + proc.stdout).lower()
            )
        ):
            self._system_prompt_unsupported = True
            proc = _one(with_sp=False)

        # Retry once on empty stdout — occasionally observed on cold start.
        if proc.returncode == 0 and not proc.stdout.strip():
            proc = _one(with_sp=not self._system_prompt_unsupported)

        if proc.returncode != 0:
            raise RuntimeError(
                f"docker exec claude -p failed (rc={proc.returncode}): "
                f"{proc.stderr[:500] or proc.stdout[:500]}"
            )
        if not proc.stdout.strip():
            raise RuntimeError("docker exec claude -p produced empty stdout twice")
        # stream-json produces one JSON object per line; aggregate into a
        # single dict so downstream parsers (extract_viewed_paths) can walk
        # it generically. The final ``type: result`` line is merged at top
        # level; everything else is collected under ``events``.
        events: list[dict] = []
        final: dict = {}
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            events.append(obj)
            if isinstance(obj, dict) and obj.get("type") == "result":
                final = dict(obj)
        final["events"] = events
        return final

    def close(self) -> None:
        if not self._started:
            return
        subprocess.run(
            ["docker", "rm", "-f", self.container_name],
            capture_output=True,
            check=False,
        )
        self._started = False


def get_runner(backend: str | None = None) -> ClaudeRunner:
    """Build a ``ClaudeRunner`` from ``backend`` or ``SCITEX_DEV_AGENTIC_BACKEND``.

    ``backend`` ∈ {``"host"``, ``"docker"``}. Defaults to ``"host"``.
    """
    choice = (backend or os.environ.get("SCITEX_DEV_AGENTIC_BACKEND") or "host").lower()
    if choice == "host":
        return HostRunner()
    if choice == "docker":
        return NewbieDockerRunner()
    raise ValueError(
        f"Unknown agentic-testing backend {choice!r}; expected 'host' or 'docker'"
    )


def extract_viewed_paths(result_json: dict | list) -> list[str]:
    """Extract skill/file references from tool-use blocks.

    Returns a flat list of strings describing which skills or files the
    agent consulted. Two sources contribute:

    1. ``view``/``Read`` tool calls — the raw ``path``/``file_path``
       argument is included as-is. Used when the agent explicitly opens a
       ``SKILL.md``.
    2. ``Skill`` tool calls — modern Claude Code loads a skill via the
       first-class ``Skill(skill=..., args=...)`` tool rather than by
       reading ``SKILL.md``. We synthesise a path ``"<skill>/SKILL.md"``
       so downstream matchers (which compare against strings like
       ``"scitex-io/SKILL.md"``) work uniformly across both execution
       paths.

    Walks the entire payload generically so it tolerates stream-json
    aggregated envelopes as well as single-result envelopes.
    """
    paths: list[str] = []
    for entry in _walk(result_json):
        if not (isinstance(entry, dict) and entry.get("type") == "tool_use"):
            continue
        name = entry.get("name", "")
        inp = entry.get("input", {}) or {}
        if name in {"view", "Read"}:
            p = inp.get("path") or inp.get("file_path")
            if p:
                paths.append(str(p))
        elif name == "Skill":
            skill = inp.get("skill")
            if skill:
                paths.append(f"{skill}/SKILL.md")
    return paths


def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


# hook-bypass: line-limit (split tracked in GITIGNORED/REFACTORING.md)
def _extract_answer_text(result: dict) -> str:
    """Final assistant text from a claude -p JSON envelope."""
    if not isinstance(result, dict):
        return ""
    r = result.get("result")
    return r if isinstance(r, str) else ""


def run_trigger_case(
    pool: ClaudeRunner,
    case: EvalCase,
    model: str = DEFAULT_MODEL,
    runs: int = RUNS_PER_CASE,
) -> TriggerResult:
    """Score hard + soft triggers. Pass = hard OR soft (positive cases)."""
    runs_out: list[bool] = []
    views_out: list[list[str]] = []
    answers_out: list[str] = []
    hard_out: list[bool] = []
    soft_out: list[bool] = []

    for _ in range(runs):
        result = pool.run(case.query, model=model)
        viewed = extract_viewed_paths(result)
        answer = _extract_answer_text(result)
        views_out.append(viewed)
        answers_out.append(answer)

        if case.expected_skill is None:
            hard_ok = not any("SKILL.md" in p for p in viewed)
        else:
            hard_ok = any(case.expected_skill in p for p in viewed)
        hard_out.append(hard_ok)

        soft_ok = bool(case.answer_contains) and all(
            s in answer for s in (case.answer_contains or [])
        )
        soft_out.append(soft_ok)

        if case.expected_skill is None:
            runs_out.append(hard_ok)  # negatives: only hard
        else:
            runs_out.append(hard_ok or soft_ok)

    return TriggerResult(
        case=case,
        runs=runs_out,
        viewed_paths_per_run=views_out,
        answers_per_run=answers_out,
        hard_trigger_per_run=hard_out,
        soft_trigger_per_run=soft_out,
    )


def load_eval_set(path: Path) -> list[EvalCase]:
    data = json.loads(Path(path).read_text())
    return [EvalCase(**c) for c in data["evals"]]
