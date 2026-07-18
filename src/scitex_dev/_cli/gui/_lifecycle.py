#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`scitex-dev gui {open,serve,status,stop}` — the canonical §12 verbs.

Process lifecycle is delegated wholesale to
:class:`scitex_dev.gui_runtime.GuiRuntime` — the shared primitive
extracted precisely so no package hand-rolls state-file/pid-liveness
bookkeeping again (doctrine
``_skills/general/03_interface/02_cli/19_gui-commands.md``). Nothing in
this module reimplements liveness; it only adds the CLI skin and the
tri-state honesty layer described below.

**Tri-state `status`.** ``GuiRuntime.status()`` is deliberately binary:
running or not. That is the right contract for the primitive (a stale
file IS a not-running server), but a CLI must not turn a *failed probe*
into a confident "not running". :func:`probe_status` therefore wraps it
and reports ``unknown`` whenever the evidence is inconclusive — the
state file exists but cannot be read/parsed, the filesystem check
itself raises, or no state file exists yet something is already
listening on the port (a server we did not start, or one started before
this state file existed). Only a readable "no state file + free port"
yields a confident ``stopped``.

**Port.** The doctrine's 3129X block is fully allocated (31290-31299 are
spoken for by storage/crossref/openalex/audio/hub/figrecipe/scholar/
writer/todo), and scitex-dev has no slot in it. Rather than squat on a
peer's port, the dashboard keeps its historical 8050 — which also means
`ecosystem start-dashboard` callers see no port change across this
migration.
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand

GUI_DEFAULT_PORT = 8050
GUI_DEFAULT_HOST = "0.0.0.0"
_PROBE_TIMEOUT_S = 0.5
_STARTUP_TIMEOUT_S = 15.0

__all__ = ["gui_state_path", "probe_status", "register", "run_server"]


def gui_state_path() -> Path:
    """Resolve the GUI runtime state file (`~/.scitex/dev/runtime/gui.json`).

    Uses the shared local-state helper when available so the runtime
    directory is created with the ecosystem's own conventions
    (`01_arch_06_local-state-directories.md`); falls back to the literal
    path when `scitex_config` is not importable, because a missing
    optional dependency must not make `gui status` unusable.

    ``$SCITEX_DEV_GUI_STATE`` overrides both. It exists because the
    helper's project-scope lookup keys off the CWD, so neither `$HOME`
    nor a temp dir is enough to point one invocation at its own state
    file — needed to run two instances side by side, and the seam the
    tests use instead of patching this function.
    """
    override = os.environ.get("SCITEX_DEV_GUI_STATE")
    if override:
        path = Path(override).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    try:
        from scitex_config._ecosystem import local_state

        return Path(local_state.runtime_path("dev")) / "gui.json"
    except Exception:
        path = Path.home() / ".scitex" / "dev" / "runtime" / "gui.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


def _runtime():
    from ...gui_runtime import GuiRuntime

    return GuiRuntime(gui_state_path())


def _connect_host(host: str) -> str:
    """The address to *dial* for a server bound to ``host``.

    `0.0.0.0` / `::` are bind-wildcards, not destinations — probing them
    is not portable, so dial loopback instead.
    """
    return "127.0.0.1" if host in ("0.0.0.0", "::", "") else host


def _port_bound(host: str, port: int) -> tuple[bool | None, str]:
    """Is something accepting connections on ``host:port``?

    Returns ``(True|False|None, detail)`` — ``None`` means the probe
    itself failed and the caller must NOT conclude anything from it.
    """
    try:
        with socket.create_connection(
            (_connect_host(host), port), timeout=_PROBE_TIMEOUT_S
        ):
            return True, "connection accepted"
    except (ConnectionRefusedError, socket.gaierror):
        return False, "connection refused"
    except socket.timeout:
        return None, "probe timed out"
    except OSError as exc:
        return None, f"probe failed: {exc}"


def probe_status(host: str = GUI_DEFAULT_HOST, port: int = GUI_DEFAULT_PORT) -> dict:
    """Tri-state liveness report: ``running`` / ``stopped`` / ``unknown``.

    See the module docstring for why ``unknown`` exists at all.
    """
    runtime = _runtime()
    path = runtime.path
    try:
        exists = path.is_file()
    except OSError as exc:
        return {
            "state": "unknown",
            "reason": f"cannot stat state file {path}: {exc}",
            "state_file": str(path),
        }

    if exists:
        if runtime.read_state() is None:
            return {
                "state": "unknown",
                "reason_code": "corrupt-state",
                "reason": (
                    f"state file {path} exists but is unreadable or malformed "
                    "— refusing to report 'not running' from a failed read"
                ),
                "state_file": str(path),
            }
        current = runtime.status()
        if current.get("running"):
            return {"state": "running", "state_file": str(path), **current}
        return {
            "state": "stopped",
            "reason": "recorded pid is no longer alive; stale state file cleared",
            "stale_state_cleared": bool(current.get("stale_state_cleared")),
            "state_file": str(path),
        }

    bound, detail = _port_bound(host, port)
    if bound is None:
        return {
            "state": "unknown",
            "reason_code": "probe-inconclusive",
            "reason": (
                f"no state file and the port probe was inconclusive ({detail}) "
                "— this CLI started nothing, but cannot rule out a server it "
                "did not start"
            ),
            "state_file": str(path),
            "port": port,
        }
    if bound:
        return {
            "state": "unknown",
            "reason_code": "foreign-listener",
            "reason": (
                f"no state file, but {_connect_host(host)}:{port} is already "
                "accepting connections — a server this CLI did not start"
            ),
            "state_file": str(path),
            "port": port,
        }
    return {"state": "stopped", "state_file": str(path), "port": port}


def run_server(host: str, port: int, debug: bool = False) -> None:
    """Serve the dashboard in the FOREGROUND, registering runtime state.

    Module-level (not a closure) so the background spawn in `gui open`
    can name it in a `python -c` child: the child must register its OWN
    pid, which is exactly what makes `gui status` / `gui stop` work for
    an auto-served instance.
    """
    runtime = _runtime()
    runtime.write_state(os.getpid(), port, host, surface="web")
    try:
        from ...dashboard import run_dashboard

        run_dashboard(
            port=port, host=host, debug=debug, open_browser=False, force=False
        )
    finally:
        runtime.clear_state()


def _spawn_server(host: str, port: int, debug: bool) -> int:
    """Start a detached server child; return its pid."""
    import subprocess

    inline = (
        "from scitex_dev._cli.gui._lifecycle import run_server; "
        f"run_server({host!r}, {port!r}, {debug!r})"
    )
    log_path = gui_state_path().parent / "gui.log"
    log_file = open(log_path, "a", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-c", inline],
        stdout=log_file,
        stderr=log_file,
        start_new_session=True,
    )
    return proc.pid


def _wait_until_serving(host: str, port: int, pid: int) -> bool:
    """Wait for the freshly-spawned server to come up.

    The state file the child writes is the PRIMARY signal, not the port
    probe: a sandbox that filters loopback SYNs (containers commonly do)
    makes the probe permanently inconclusive, and a readiness check must
    not depend on a capability the environment may not have. The probe
    is only consulted as a fast positive confirmation.
    """
    import time

    from ...gui_runtime import pid_alive

    runtime = _runtime()
    deadline = time.monotonic() + _STARTUP_TIMEOUT_S
    while time.monotonic() < deadline:
        bound, _ = _port_bound(host, port)
        if bound:
            return True
        state = runtime.read_state()
        if state is not None and state.get("pid") == pid and pid_alive(pid):
            return True
        if not pid_alive(pid):
            return False
        time.sleep(0.25)
    return False


def _emit_status(report: dict, as_json: bool) -> None:
    if as_json:
        import json

        click.echo(json.dumps(report, indent=2, default=str))
        return
    state = report["state"]
    if state == "running":
        click.echo(f"running: {report.get('url')} (pid {report.get('pid')})")
        click.echo(f"  started: {report.get('started_at')}")
    elif state == "stopped":
        click.echo("not running")
    else:
        click.echo("UNKNOWN — cannot determine whether the GUI is running")
    reason = report.get("reason")
    if reason and state != "running":
        click.echo(f"  {reason}")
    click.echo(f"  state file: {report.get('state_file')}")


def register(gui: click.Group) -> None:
    """Attach the four canonical verbs to the `gui` group."""

    @gui.command(
        "open",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Open a GUI surface in the browser, auto-serving it first.",
            description=(
                "SURFACE defaults to `web` (the ecosystem dashboard), the "
                "only browser surface scitex-dev currently ships. The "
                "server is started detached if it is not already running, "
                "so the shell returns immediately; use `gui serve` when "
                "you want a foreground, headless server instead."
            ),
            examples=(
                Example("{prog} gui open", "Serve if needed, then open a browser."),
                Example("{prog} gui open web --port 9000", "Non-default port."),
                Example("{prog} gui open --dry-run", "Show what would happen."),
            ),
        ),
    )
    @click.argument("surface", required=False, default="web")
    @click.option(
        "--port", default=GUI_DEFAULT_PORT, show_default=True, type=int,
        help="Port to serve on.",
    )
    @click.option(
        "--host", default=GUI_DEFAULT_HOST, show_default=True, help="Host to bind to."
    )
    @click.option("--force", is_flag=True, help="Kill any process holding the port first.")
    @click.option(
        "--debug", is_flag=True, hidden=True,
        help="Legacy passthrough from `ecosystem start-dashboard`: Flask debug mode.",
    )
    @click.option(
        "--no-browser", is_flag=True, hidden=True,
        help=(
            "Legacy passthrough from `ecosystem start-dashboard`: ensure the "
            "server is up but do not launch a browser."
        ),
    )
    @click.option(
        "--background", is_flag=True, hidden=True,
        help=(
            "Legacy passthrough from `ecosystem start-dashboard`: accepted "
            "and ignored — `gui open` always serves detached."
        ),
    )
    @click.option("--dry-run", is_flag=True, help="Print the plan; start nothing.")
    @click.option("-y", "--yes", is_flag=True, help="Confirm; nothing to prompt for.")
    def gui_open(surface, port, host, force, debug, no_browser, background, dry_run, yes):
        del yes, background  # accepted for §2 / legacy compatibility
        if surface != "web":
            raise click.ClickException(
                f"unknown surface {surface!r} — scitex-dev ships one browser "
                "surface: `web` (the ecosystem dashboard)"
            )
        if dry_run:
            click.echo(
                f"would ensure the {surface} GUI is serving on {host}:{port} "
                f"(force={force}, debug={debug}) and "
                f"{'skip the browser' if no_browser else 'open a browser'}"
            )
            return

        report = probe_status(host, port)
        if force and report["state"] != "stopped":
            from ...dashboard.app import _kill_process_on_port

            _kill_process_on_port(port)
            _runtime().clear_state()
            report = probe_status(host, port)

        url = report.get("url") or f"http://{_connect_host(host)}:{port}"
        if report["state"] == "running":
            click.echo(f"already serving at {url}")
        elif report.get("reason_code") in ("corrupt-state", "foreign-listener"):
            # Positive evidence of something we do not own. Refuse rather
            # than stack a second server on the same port.
            click.echo(f"status is UNKNOWN — {report.get('reason')}", err=True)
            click.echo(
                "refusing to auto-serve on top of it; re-run with --force to "
                "take over the port, or run `gui status` for detail.",
                err=True,
            )
            raise SystemExit(2)
        else:
            # `stopped`, or `unknown` only because the port probe could not
            # reach a verdict — no evidence of a running instance, so serve.
            # A genuine conflict then surfaces as a loud bind error.
            if report["state"] == "unknown":
                click.echo(f"note: {report.get('reason')}", err=True)
            pid = _spawn_server(host, port, debug)
            if not _wait_until_serving(host, port, pid):
                raise click.ClickException(
                    f"server (pid {pid}) did not start accepting connections "
                    f"within {_STARTUP_TIMEOUT_S:.0f}s — see "
                    f"{gui_state_path().parent / 'gui.log'}"
                )
            click.echo(f"serving at {url} (pid {pid})")

        if no_browser:
            return
        import webbrowser

        webbrowser.open(url)

    @gui.command(
        "serve",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Run the GUI server in the foreground (headless).",
            description=(
                "Blocks until Ctrl-C. Never opens a browser — that is "
                "exclusively `gui open`'s job. Runtime state is registered "
                "on start and cleared on exit, so `gui status` and "
                "`gui stop` see this instance too."
            ),
            examples=(
                Example("{prog} gui serve", "Foreground server on the default port."),
                Example("{prog} gui serve --port 9000 --host 127.0.0.1", "Loopback only."),
            ),
        ),
    )
    @click.option(
        "--port", default=GUI_DEFAULT_PORT, show_default=True, type=int,
        help="Port to serve on.",
    )
    @click.option(
        "--host", default=GUI_DEFAULT_HOST, show_default=True, help="Host to bind to."
    )
    @click.option("--debug", is_flag=True, help="Enable Flask debug/reload mode.")
    @click.option("--force", is_flag=True, help="Kill any process holding the port first.")
    @click.option("--dry-run", is_flag=True, help="Print the plan; serve nothing.")
    def gui_serve(port, host, debug, force, dry_run):
        if dry_run:
            click.echo(f"would serve on {host}:{port} (debug={debug}, force={force})")
            return
        if force:
            from ...dashboard.app import _kill_process_on_port

            _kill_process_on_port(port)
            _runtime().clear_state()
        run_server(host, port, debug)

    @gui.command(
        "status",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Report whether the GUI is running, and where.",
            description=(
                "Tri-state by design: `running`, `not running`, or "
                "`UNKNOWN`. UNKNOWN is reported whenever the evidence is "
                "inconclusive — an unreadable state file, a failed port "
                "probe, or a port already bound by a server this CLI did "
                "not start. A confident 'not running' is never derived "
                "from a probe that failed."
            ),
            examples=(
                Example("{prog} gui status", "Human-readable state."),
                Example("{prog} gui status --json", "Structured state for scripts."),
            ),
        ),
    )
    @click.option(
        "--port", default=GUI_DEFAULT_PORT, show_default=True, type=int,
        help="Port to probe when no state file exists.",
    )
    @click.option(
        "--host", default=GUI_DEFAULT_HOST, show_default=True, help="Host to probe."
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def gui_status(port, host, as_json):
        _emit_status(probe_status(host, port), as_json)

    @gui.command(
        "stop",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Stop the running GUI instance.",
            description=(
                "SIGTERMs the recorded server and clears its state file. "
                "Idempotent — stopping an already-stopped GUI is not an "
                "error. Also removes the legacy `dashboard.pid` file left "
                "by the pre-migration `start-dashboard --background`."
            ),
            examples=(
                Example("{prog} gui stop --yes", "Stop the running instance."),
                Example("{prog} gui stop --dry-run", "Show what would be stopped."),
            ),
        ),
    )
    @click.option("--dry-run", is_flag=True, help="Print what would be stopped.")
    @click.option("-y", "--yes", is_flag=True, help="Confirm the stop.")
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def gui_stop(dry_run, yes, as_json):
        report = probe_status()
        if dry_run:
            click.echo(
                f"would stop pid {report.get('pid')} ({report.get('url')})"
                if report["state"] == "running"
                else f"nothing to stop (state: {report['state']})"
            )
            return
        if not yes:
            click.echo("Refusing to stop the GUI without --yes/-y.", err=True)
            raise SystemExit(2)

        result = _runtime().stop()
        legacy_pid = gui_state_path().parent / "dashboard.pid"
        if legacy_pid.exists():
            legacy_pid.unlink()
            result["legacy_pidfile_removed"] = str(legacy_pid)
        if as_json:
            import json

            click.echo(json.dumps({**report, **result}, indent=2, default=str))
            return
        if result.get("stopped"):
            click.echo(f"stopped pid {result['pid']}")
            if not result.get("terminated"):
                click.echo(
                    "  warning: process was still alive after SIGTERM + grace "
                    "period; state file cleared anyway",
                    err=True,
                )
        else:
            click.echo(f"nothing to stop (state: {report['state']})")
            if report["state"] == "unknown":
                click.echo(f"  {report.get('reason')}", err=True)


# EOF
