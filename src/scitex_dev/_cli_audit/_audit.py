"""Audit engine — walks a Click command tree and classifies tokens.

Rules audited (warn-only):
- §1   noun-verb structure        (subcommand grammar)
- §1b  banned bare leaves         (`version`, `completion`)
- §1d  vocabulary in catalog/dict
- §2   universal flag presence    (--version/-V, --help-recursive at top;
                                   --json on read verbs; --dry-run, --yes
                                   on mutating verbs)
- §4   help format                (Usage line + at least one example)
"""

from __future__ import annotations

import gzip
import importlib.metadata as im
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path

import click
import yaml

from . import CATALOG, FLAT_KEEPERS

# §5/§1b banned bare leaves at any depth.
BANNED_LEAVES = {"version", "completion"}


# ----------------------------------------------------------------------- #
# Registry loader (per §6b config-precedence cascade for `scitex-dev`)    #
# ----------------------------------------------------------------------- #

REGISTRY_CASCADE_DOC = """\
Registry resolution (highest priority first):
\b
  1. --registry PATH                        (CLI flag)
  2. $SCITEX_DEV_REGISTRY                   (env var)
  3. <cwd>/.scitex/dev/ecosystem.yaml       (project)
  4. ~/.scitex/dev/ecosystem.yaml           (user)
  5. bundled scitex_dev.ecosystem.ECOSYSTEM (default)

YAML override format (any layer 1-4) replaces or extends the bundled dict;
keys present in the override win, others fall through to the default."""


def _load_registry(
    explicit_path: str | Path | None = None,
) -> tuple[dict, str]:
    """Resolve the ecosystem registry per the §6b cascade.

    Returns (registry_dict, provenance_string). The provenance string names
    the layer that supplied the registry — surfaced in --help and in the
    `--all` summary so users know what they're auditing.
    """
    from .. import ecosystem as _eco

    bundled: dict = dict(_eco.ECOSYSTEM)

    candidates: list[tuple[str, Path | None]] = []
    if explicit_path:
        candidates.append(("--registry flag", Path(explicit_path).expanduser()))
    import os as _os

    env_path = _os.environ.get("SCITEX_DEV_REGISTRY")
    if env_path:
        candidates.append(("$SCITEX_DEV_REGISTRY", Path(env_path).expanduser()))
    candidates.append(
        (
            "project (.scitex/dev/ecosystem.yaml)",
            Path.cwd() / ".scitex" / "dev" / "ecosystem.yaml",
        )
    )
    candidates.append(
        (
            "user (~/.scitex/dev/ecosystem.yaml)",
            Path.home() / ".scitex" / "dev" / "ecosystem.yaml",
        )
    )

    for label, path in candidates:
        if path is None or not path.is_file():
            continue
        try:
            override = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            click.echo(
                f"warn  registry override at {path} is unreadable ({e}); falling through",
                err=True,
            )
            continue
        if not isinstance(override, dict):
            click.echo(
                f"warn  registry override at {path} must be a mapping; falling through",
                err=True,
            )
            continue
        merged = {**bundled, **override}
        return merged, f"{label}: {path}"

    return bundled, "bundled (scitex_dev.ecosystem.ECOSYSTEM)"


# Module-name fragments that mark a console-script as an MCP / protocol server,
# not a user-facing CLI. Audited separately by the future `audit-mcp-tools`.
_MCP_MODULE_FRAGMENTS = ("mcp_server", "_mcp", "_server")


def _is_mcp_server_entry(ep_value: str) -> bool:
    """True if a console-script target points at an MCP / protocol server."""
    module = ep_value.split(":", 1)[0].lower()
    return any(frag in module for frag in _MCP_MODULE_FRAGMENTS)


# Verb classes for §2 flag-presence checks.
READ_VERBS = {
    "list",
    "show",
    "get",
    "find",
    "search",
    "describe",
    "inspect",
    "diff",
    "tail",
    "status",
}
MUTATING_VERBS = {
    "create",
    "add",
    "init",
    "generate",
    "scaffold",
    "clone",
    "copy",
    "import",
    "register",
    "update",
    "edit",
    "rename",
    "move",
    "merge",
    "patch",
    "reset",
    "restore",
    "rollback",
    "delete",
    "remove",
    "purge",
    "clean",
    "archive",
    "revoke",
    "start",
    "stop",
    "restart",
    "pause",
    "resume",
    "enable",
    "disable",
    "install",
    "uninstall",
    "build",
    "compile",
    "publish",
    "deploy",
    "tag",
    "ship",
    "save",
    "write",
    "upload",
    "export",
    "convert",
    "sync",
    "pull",
    "push",
    "commit",
    "stash",
    "apply",
    "reconcile",
    "send",
    "notify",
    "broadcast",
    "fix",
}


@lru_cache(maxsize=1)
def _load_moby() -> dict[str, set[str]]:
    """Parse vendored Moby POS into {word: {labels}}.

    Labels: noun, verb, verb-t, verb-i.
    """
    db: dict[str, set[str]] = {}
    data = resources.files("scitex_dev._cli_audit").joinpath("data", "mobypos.txt.gz")
    with gzip.open(data.open("rb"), mode="rt", encoding="latin-1") as f:
        for line in f:
            if "\\" not in line:
                continue
            word, pos = line.rstrip("\n").rsplit("\\", 1)
            word = word.lower()
            tags: set[str] = set()
            for c in pos:
                if c == "N":
                    tags.add("noun")
                elif c == "V":
                    tags.add("verb")
                elif c == "t":
                    tags.add("verb-t")
                elif c == "i":
                    tags.add("verb-i")
            if tags:
                db.setdefault(word, set()).update(tags)
    return db


def _load_custom_dict() -> dict[str, set[str]]:
    """Merge project + user custom dictionaries."""
    out: dict[str, set[str]] = {}
    candidates = [
        Path.cwd() / ".scitex" / "dev" / "cli-audit-dict.yaml",
        Path.home() / ".scitex" / "dev" / "cli-audit-dict.yaml",
    ]
    for path in reversed(candidates):
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError:
            continue
        for tag, key in [
            ("noun", "nouns"),
            ("verb-t", "transitive_verbs"),
            ("verb-i", "intransitive_verbs"),
        ]:
            for w in data.get(key, []) or []:
                out.setdefault(w.lower(), set()).add(tag)
    return out


def _singular_candidates(word: str) -> list[str]:
    """Return likely singular forms of `word` (cheapest English heuristic)."""
    out: list[str] = []
    if word.endswith("ies") and len(word) > 3:
        out.append(word[:-3] + "y")  # bibentries -> bibentry
    if word.endswith("ses") and len(word) > 3:
        out.append(word[:-2])  # caches -> cache
    if word.endswith("es") and len(word) > 2:
        out.append(word[:-2])  # passes -> pass
    if word.endswith("s") and len(word) > 1:
        out.append(word[:-1])  # jobs -> job
    return out


def _classify(token: str) -> set[str]:
    """Return labels for a token using layered lookup, with plural fall-through."""
    token_lc = token.lower()
    first = token_lc.split("-")[0]

    custom = _load_custom_dict()
    if token_lc in custom:
        return set(custom[token_lc])
    if first in custom:
        return set(custom[first])

    if token_lc in CATALOG:
        return set(CATALOG[token_lc])
    if first in CATALOG:
        return set(CATALOG[first])

    moby = _load_moby()
    if token_lc in moby:
        return set(moby[token_lc])
    if first in moby:
        return set(moby[first])

    # Plural fall-through — `packages` → `package`. Only inherits the noun
    # label (a plural verb form is rare and would be picked up by Moby above).
    for candidate in _singular_candidates(token_lc):
        for source in (custom, CATALOG, moby):
            labels = source.get(candidate)
            if labels and "noun" in labels:
                return {"noun"}
    for candidate in _singular_candidates(first):
        for source in (custom, CATALOG, moby):
            labels = source.get(candidate)
            if labels and "noun" in labels:
                return {"noun"}

    return {"unknown"}


@dataclass
class Violation:
    command: str
    rule: str
    message: str


def _verb_token(name: str) -> str:
    """Extract the verb token from a leaf name.

    For tree leaves the leaf name *is* the verb (e.g. `list`).
    For compound leaves (`<verb>-<noun>`), the head is the verb (e.g. `start-dashboard`).
    """
    return name.lower().split("-")[0]


def _flag_names(cmd: click.BaseCommand) -> set[str]:
    """All flag spellings declared on a command (`--foo`, `-f`)."""
    out: set[str] = set()
    for p in getattr(cmd, "params", []) or []:
        for opt in getattr(p, "opts", []) or []:
            out.add(opt)
        for opt in getattr(p, "secondary_opts", []) or []:
            out.add(opt)
    return out


def _has_example(cmd: click.BaseCommand) -> bool:
    """§4 — concrete example detection.

    Stricter than a substring sniff: requires either
      - an `Examples:` / `Example:` header followed by content, or
      - a literal command-line invocation (`$ <cli> ...`), or
      - a fenced code block (```), or
      - a callable .. code-block:: directive.
    """
    blocks = []
    for attr in ("help", "epilog"):
        v = getattr(cmd, attr, None)
        if v:
            blocks.append(v)
    text = "\n".join(blocks)
    if not text:
        return False
    if re.search(r"(?im)^\s*examples?:\s*$", text):
        return True
    if re.search(r"(?m)^\s*\$\s+\S", text):
        return True
    if "```" in text:
        return True
    if ".. code-block::" in text:
        return True
    return False


def _is_pass_through(cmd: click.BaseCommand) -> bool:
    """§1c — verbatim-forwarding entry point detection.

    Two signals:
      1. Click `context_settings={"ignore_unknown_options": True, "allow_extra_args": True}`.
      2. A `_pass_through = True` attribute on the command (sentinel for non-Click cases
         and for explicit declarations).
    """
    if getattr(cmd, "_pass_through", False):
        return True
    cs = getattr(cmd, "context_settings", None) or {}
    return bool(cs.get("ignore_unknown_options")) and bool(cs.get("allow_extra_args"))


def _check_help_format(cmd: click.BaseCommand, full: str, out: list[Violation]) -> None:
    """§4 — help must include Usage synopsis (Click adds automatically) + an example.

    Click guarantees the Usage line, so we only check for an example marker.
    """
    if isinstance(cmd, click.Group):
        # Groups list subcommands; examples live on leaves.
        return
    if not _has_example(cmd):
        out.append(
            Violation(
                full,
                "§4",
                "help has no concrete example — add one to the docstring "
                "or Click epilog (e.g. 'Example:\\n  $ <cli> <noun> <verb> ...')",
            )
        )


def _check_universal_flags(
    cmd: click.BaseCommand, full: str, is_root: bool, out: list[Violation]
) -> None:
    """§2 — universal flag presence."""
    flags = _flag_names(cmd)

    if is_root:
        if not ({"--version", "-V"} & flags):
            out.append(
                Violation(
                    full,
                    "§2",
                    "top-level missing --version/-V flag",
                )
            )
        if "--help-recursive" not in flags:
            out.append(
                Violation(
                    full,
                    "§2",
                    "top-level missing --help-recursive flag",
                )
            )
        return

    # Leaf-only flag checks; groups themselves are read-like dispatchers.
    if isinstance(cmd, click.Group):
        return

    name = cmd.name or ""
    verb = _verb_token(name)

    if verb in READ_VERBS and "--json" not in flags:
        out.append(
            Violation(
                full,
                "§2",
                f"read verb '{verb}' missing --json flag (machine-readable output)",
            )
        )
    if verb in MUTATING_VERBS:
        if "--dry-run" not in flags:
            out.append(
                Violation(
                    full,
                    "§2",
                    f"mutating verb '{verb}' missing --dry-run flag",
                )
            )
        if not ({"--yes", "-y"} & flags):
            out.append(
                Violation(
                    full,
                    "§2",
                    f"mutating verb '{verb}' missing --yes/-y flag",
                )
            )


def _walk(
    cmd: click.BaseCommand,
    path: list[str],
    out: list[Violation],
    root_display: str,
) -> None:
    # Skip hidden commands — not part of the public CLI surface
    # (typically deprecation redirects kept for back-compat).
    if getattr(cmd, "hidden", False):
        return
    is_root = not path
    name = root_display if is_root else (cmd.name or "<root>")
    full = " ".join(path + [name]) if path else name
    is_group = isinstance(cmd, click.Group)

    # §2 universal flag presence.
    _check_universal_flags(cmd, full, is_root, out)

    if not is_root:
        # §1c — pass-through entry points are exempt from §1 / §1d / §4.
        if _is_pass_through(cmd):
            return

        labels = _classify(name)
        is_leaf = not is_group
        is_compound = "-" in name

        # §1b banned bare leaves.
        if is_leaf and name.lower() in BANNED_LEAVES:
            redirect = {
                "version": "use the --version/-V flag at top level",
                "completion": "use 'install-shell-completion' or 'print-shell-completion'",
            }[name.lower()]
            out.append(
                Violation(full, "§1b", f"banned bare leaf '{name}' — {redirect}")
            )

        if is_leaf:
            if (
                "noun" in labels
                and not ({"verb-t", "verb-i", "verb", "flat-keeper"} & labels)
                and name not in FLAT_KEEPERS
            ):
                out.append(
                    Violation(
                        full,
                        "§1",
                        f"leaf token looks like a noun — transitive action implied; "
                        f"use '<verb>-{name}' (e.g. start-{name}) or add a sibling verb",
                    )
                )
            if (
                ("verb-t" in labels or "verb" in labels)
                and not is_compound
                and len(path) == 1
                and "noun" not in labels
            ):
                out.append(
                    Violation(
                        full,
                        "§1",
                        f"bare transitive verb at top level — needs an object; "
                        f"use '{name}-<object>' or nest under a noun",
                    )
                )
        else:
            if ({"verb-t", "verb-i", "verb"} & labels) and "noun" not in labels:
                out.append(
                    Violation(
                        full,
                        "§1",
                        "group token looks like a verb — non-leaf subcommands must be nouns",
                    )
                )

        if labels == {"unknown"}:
            out.append(
                Violation(
                    full,
                    "§1d",
                    f"'{name}' not in catalog, custom dict, or Moby POS — "
                    f"add to .scitex/dev/cli-audit-dict.yaml or rename",
                )
            )

        # §4 help format on leaves.
        _check_help_format(cmd, full, out)

    if is_group:
        next_path = [name] if is_root else path + [name]
        for sub in cmd.commands.values():
            _walk(sub, next_path, out, root_display)


# --------------------------------------------------------------------- #
# argparse adapter — wrap an argparse.ArgumentParser tree as click nodes #
# --------------------------------------------------------------------- #


class _SyntheticOption:
    """Minimal Click-Option duck-type for `_flag_names()`."""

    def __init__(self, opts: list[str]):
        self.opts = list(opts)
        self.secondary_opts: list[str] = []


class _ArgparseLeaf(click.Command):
    """Click.Command wrapper around a leaf argparse parser."""

    def __init__(self, name, help_text, epilog, params_):
        super().__init__(
            name=name,
            callback=lambda: None,
            help=help_text or None,
            epilog=epilog or None,
        )
        self.params = params_  # type: ignore[assignment]


class _ArgparseGroup(click.Group):
    """Click.Group wrapper around an argparse parser with subparsers."""

    def __init__(self, name, help_text, epilog, params_, commands):
        super().__init__(
            name=name,
            callback=lambda: None,
            help=help_text or None,
            epilog=epilog or None,
        )
        self.params = params_  # type: ignore[assignment]
        self.commands = commands


def _argparse_subcommands(parser) -> dict[str, object]:
    import argparse as _ap

    out: dict[str, object] = {}
    for action in getattr(parser, "_actions", []) or []:
        if isinstance(action, _ap._SubParsersAction):
            for name, sp in action.choices.items():
                out[name] = sp
    return out


def _argparse_flag_params(parser) -> list[_SyntheticOption]:
    import argparse as _ap

    params: list[_SyntheticOption] = []
    for action in getattr(parser, "_actions", []) or []:
        if isinstance(action, _ap._SubParsersAction):
            continue
        if not getattr(action, "option_strings", None):
            continue  # positional argument
        params.append(_SyntheticOption(list(action.option_strings)))
    return params


def _wrap_argparse(parser, name: str | None = None) -> click.BaseCommand:
    name = name or getattr(parser, "prog", None) or "<root>"
    name = name.split()[0] if isinstance(name, str) else "<root>"
    help_text = (getattr(parser, "description", "") or "").strip()
    epilog = (getattr(parser, "epilog", "") or "").strip()
    params = _argparse_flag_params(parser)
    children_raw = _argparse_subcommands(parser)
    if children_raw:
        commands = {n: _wrap_argparse(sp, n) for n, sp in children_raw.items()}
        return _ArgparseGroup(name, help_text, epilog, params, commands)
    return _ArgparseLeaf(name, help_text, epilog, params)


class _StopBeforeParse(Exception):
    """Sentinel used to abort `main()` once it constructs its argparse parser."""


import contextlib as _contextlib  # noqa: E402  -- needed by the helpers below


@_contextlib.contextmanager
def _intercept_parse_calls(captured: list[object]):
    """Patch `argparse.ArgumentParser.parse_args/parse_known_args` and
    `click.BaseCommand.main` to capture the receiver and raise
    `_StopBeforeParse` instead of actually executing the CLI.

    Any list passed in receives one append per intercepted call.

    Restores all three patched methods on exit, even if the wrapped block raises.
    """
    import argparse as _ap

    real_pa = _ap.ArgumentParser.parse_args
    real_pka = _ap.ArgumentParser.parse_known_args
    real_click_main = click.BaseCommand.main

    def _fake_pa(self, *a, **kw):
        captured.append(self)
        raise _StopBeforeParse()

    def _fake_pka(self, *a, **kw):
        captured.append(self)
        raise _StopBeforeParse()

    def _fake_click_main(self, *a, **kw):
        captured.append(self)
        raise _StopBeforeParse()

    _ap.ArgumentParser.parse_args = _fake_pa  # type: ignore[assignment]
    _ap.ArgumentParser.parse_known_args = _fake_pka  # type: ignore[assignment]
    click.BaseCommand.main = _fake_click_main  # type: ignore[assignment]
    try:
        yield
    finally:
        _ap.ArgumentParser.parse_args = real_pa  # type: ignore[assignment]
        _ap.ArgumentParser.parse_known_args = real_pka  # type: ignore[assignment]
        click.BaseCommand.main = real_click_main  # type: ignore[assignment]


class _PackageTimeout(Exception):
    """Raised when a single package's audit exceeds the watchdog window."""


@_contextlib.contextmanager
def _watchdog(seconds: float):
    """SIGALRM-based watchdog (Unix, main-thread only).

    Wraps a slow-or-hung `_audit_one` call in `run_audit_all` so a single
    bad package can't wedge the ecosystem run. On non-Unix or off-main-thread,
    silently no-ops so behavior degrades to the prior (no-watchdog) baseline.
    """
    import signal as _signal
    import threading as _threading

    if (
        not hasattr(_signal, "SIGALRM")
        or _threading.current_thread() is not _threading.main_thread()
        or seconds <= 0
    ):
        yield
        return

    def _handler(signum, frame):
        raise _PackageTimeout()

    prev_handler = _signal.signal(_signal.SIGALRM, _handler)
    _signal.setitimer(_signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        _signal.setitimer(_signal.ITIMER_REAL, 0)
        _signal.signal(_signal.SIGALRM, prev_handler)


@_contextlib.contextmanager
def _isolated_streams():
    """Run a block with stdin/stdout/stderr redirected to /dev/null.

    MCP-server entry points often close stdio on import or write protocol
    frames to stdout — the auditor's reporter streams must survive that.
    On exit, sys.stdout/stderr are restored to the original interpreter
    streams (via os.fdopen on fds 1/2 if the saved streams were closed).
    """
    import os as _os
    import sys as _sys

    real_stdin = _sys.stdin
    real_out, real_err = _sys.__stdout__, _sys.__stderr__
    devnull_in = open(_os.devnull, "r")
    devnull_out = open(_os.devnull, "w")
    saved_stdin = _sys.stdin
    _sys.stdin = devnull_in
    try:
        with (
            _contextlib.redirect_stdout(devnull_out),
            _contextlib.redirect_stderr(devnull_out),
        ):
            yield
    finally:
        _sys.stdin = real_stdin if not real_stdin.closed else saved_stdin
        # `closefd=False` is essential: without it, the wrapper's eventual GC
        # would close the inherited fd 1/2 and break every subsequent write
        # (including `click.echo` output of later violations and the summary).
        if real_out is None or real_out.closed:
            _sys.stdout = _os.fdopen(1, "w", closefd=False)
        else:
            _sys.stdout = real_out
        if real_err is None or real_err.closed:
            _sys.stderr = _os.fdopen(2, "w", closefd=False)
        else:
            _sys.stderr = real_err
        try:
            devnull_in.close()
        except Exception:
            pass
        try:
            devnull_out.close()
        except Exception:
            pass


def _capture_root(callable_obj):
    """Invoke `callable_obj` with parse calls intercepted; return the captured
    root command — either an `argparse.ArgumentParser` or a `click.BaseCommand`.

    Catches the common patterns:
      - `def main(argv): parser=...; parser.parse_args(argv)`  (argparse)
      - `def main(): cli()`                                    (Click, lazy import)
      - `def main(): app.main(args=[])`                        (Click, explicit)

    Returns None if no parse call was triggered.

    The patching contract (assumed by every checker that calls this):
      1. argparse.ArgumentParser.parse_args / parse_known_args raise _StopBeforeParse
         after appending `self` to the captured list.
      2. click.BaseCommand.main does the same.
      3. sys.argv is set to a single-element list to avoid leaking real args.
      4. All three originals are restored even on exception.

    Limitation — multi-parser CLIs:
      Only the **first** parser whose `parse_args` is invoked is captured.
      A `def main(): outer.parse_args(); inner.parse_args()` shape would
      lose `inner`. No real ecosystem package does this today, but if one
      shows up the fix is to extend `_intercept_parse_calls` to keep
      collecting after the first hit and rank candidates by `_actions` count.
    """
    import sys as _sys

    captured: list[object] = []
    saved_argv = _sys.argv
    _sys.argv = [getattr(callable_obj, "__name__", "cli")]
    try:
        with _intercept_parse_calls(captured):
            # Try `main(argv)` then `main()` — different conventions in the wild.
            for invocation in (lambda: callable_obj([]), lambda: callable_obj()):
                try:
                    invocation()
                except _StopBeforeParse:
                    break
                except TypeError:
                    continue  # signature mismatch; try the other shape
                except SystemExit:
                    if captured:
                        break
                except BaseException:
                    if captured:
                        break
                if captured:
                    break
    finally:
        _sys.argv = saved_argv
    return captured[0] if captured else None


def _resolve_entry_point(package: str) -> click.BaseCommand | None:
    """Find the root command for an entry-point name.

    Tries, in order:
      1. Entry point itself is a click.BaseCommand.
      2. Entry point is a wrapper `def main(): app()` — scan its module for
         a module-level click.BaseCommand.
      3. Entry point is a `def main(argv): parser=...; parser.parse_args(argv)`
         (argparse) — capture the parser and wrap it as a Click-shaped tree.
      4. Otherwise → not auditable.
    """
    import importlib

    try:
        eps = im.entry_points(group="console_scripts")
    except TypeError:
        eps = im.entry_points().get("console_scripts", [])
    matching = [ep for ep in eps if ep.name == package]
    if not matching:
        return None

    last_err: str | None = None
    for ep in matching:
        try:
            obj = ep.load()
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            continue
        if isinstance(obj, click.BaseCommand):
            return obj

        # Wrapper function — scan its module for a click root.
        mod_name = getattr(obj, "__module__", None)
        if mod_name:
            try:
                mod = importlib.import_module(mod_name)
            except Exception:
                mod = None
            if mod is not None:
                for attr in ("cli", "app", "main_cli", "root", "main"):
                    val = getattr(mod, attr, None)
                    if isinstance(val, click.BaseCommand):
                        return val
                for val in vars(mod).values():
                    if isinstance(val, click.BaseCommand):
                        return val

        # Invoke-and-capture fallback — handles both lazy-imported click roots
        # and argparse parsers built inside main().
        if callable(obj):
            root = _capture_root(obj)
            if isinstance(root, click.BaseCommand):
                return root
            if root is not None:
                return _wrap_argparse(root, name=package)

        last_err = f"not a click or argparse CLI (got {type(obj).__name__})"

    _resolve_entry_point._last_err = last_err  # type: ignore[attr-defined]
    return None


def _check_introspection(
    cmd: click.BaseCommand, package: str, out: list[Violation]
) -> None:
    """§1a — `list-python-apis` (top-level) and `mcp list-tools` must exist.

    Both must accept --json. Verbosity ladder (-v/-vv/-vvv) is checked
    behaviorally elsewhere; here we only assert presence and --json.
    """
    if not isinstance(cmd, click.Group):
        return

    sub = cmd.commands.get("list-python-apis")
    if sub is None:
        out.append(
            Violation(
                package,
                "§1a",
                "missing required top-level command 'list-python-apis'",
            )
        )
    else:
        if "--json" not in _flag_names(sub):
            out.append(
                Violation(
                    f"{package} list-python-apis",
                    "§1a",
                    "missing --json flag (required for §1a introspection)",
                )
            )

    mcp = cmd.commands.get("mcp")
    if mcp is None or not isinstance(mcp, click.Group):
        out.append(
            Violation(
                package,
                "§1a",
                "missing required 'mcp' command group with 'list-tools' subcommand",
            )
        )
        return
    list_tools = mcp.commands.get("list-tools")
    if list_tools is None:
        out.append(
            Violation(
                f"{package} mcp",
                "§1a",
                "missing required 'list-tools' subcommand under 'mcp'",
            )
        )
    elif "--json" not in _flag_names(list_tools):
        out.append(
            Violation(
                f"{package} mcp list-tools",
                "§1a",
                "missing --json flag (required for §1a introspection)",
            )
        )


def _expected_env_prefix(package: str) -> str | None:
    """Compute `SCITEX_<PKG>_` prefix for a scitex-* package.

    Returns None for non-scitex packages (out of scope per §6a).
    """
    name = package.lower()
    if name == "scitex":
        return "SCITEX_"
    if not name.startswith("scitex-"):
        return None
    short = name[len("scitex-") :].replace("-", "_").upper()
    return f"SCITEX_{short}_"


def _bare_pkg_prefix(package: str) -> str | None:
    """Forbidden bare package-name prefix (e.g. `PLT_` for scitex-plt)."""
    name = package.lower()
    if not name.startswith("scitex-"):
        return None
    return name[len("scitex-") :].replace("-", "_").upper() + "_"


# Common third-party / OS env vars that any code may legitimately read.
_ALLOWED_ENV_PREFIXES = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "TERM",
    "DISPLAY",
    "LANG",
    "LC_",
    "TZ",
    "TMPDIR",
    "TEMP",
    "TMP",
    "EDITOR",
    "PAGER",
    "PWD",
    "OLDPWD",
    "XDG_",
    "SSH_",
    "SUDO_",
    "DBUS_",
    "PYTHON",
    "VIRTUAL_ENV",
    "CONDA_",
    "PIP_",
    "PYTEST_",
    "PYTHONPATH",
    "MPLBACKEND",
    "MPLCONFIGDIR",
    "CI",
    "GITHUB_",
    "GITLAB_",
    "RUNNER_",
    "AWS_",
    "GCP_",
    "GOOGLE_",
    "AZURE_",
    "OPENAI_",
    "ANTHROPIC_",
    "HF_",
    "HUGGINGFACE_",
    "WANDB_",
    "MLFLOW_",
    "SLURM_",
    "SBATCH_",
    "OMP_",
    "MKL_",
    "OPENBLAS_",
    "NUMEXPR_",
    "CUDA_",
    "NCCL_",
    "TF_",
    "TORCH_",
    "JAX_",
    "KERAS_",
    "RAY_",
    "NO_COLOR",
    "FORCE_COLOR",
    "CLICOLOR",
    "CLICOLOR_FORCE",
    "DOCKER_",
    "PODMAN_",
    "APPTAINER_",
    "SINGULARITY_",
    "POSTGRES_",
    "MYSQL_",
    "REDIS_",
    "MONGO_",
    "DJANGO_",
    "FLASK_",
    "VITE_",
    "NODE_",
    "NPM_",
    "YARN_",
    "JUPYTER_",
    "IPYTHON",
    "READTHEDOCS",
    "RTD_",
    "SPHINX_",
    "CLAUDE_",
    "CURSOR_",
)


def _is_allowed_env(var: str) -> bool:
    return any(var == p.rstrip("_") or var.startswith(p) for p in _ALLOWED_ENV_PREFIXES)


@lru_cache(maxsize=1)
def _known_scitex_prefixes() -> tuple[str, ...]:
    """Return the set of valid `SCITEX_<PKG>_` prefixes from the bundled registry."""
    try:
        from .. import ecosystem as _eco
    except Exception:
        return ()
    out: set[str] = {"SCITEX_"}  # umbrella
    for name in _eco.ECOSYSTEM:
        prefix = _expected_env_prefix(name)
        if prefix:
            out.add(prefix)
    return tuple(sorted(out))


def _scan_env_vars(package: str, out: list[Violation]) -> None:
    """§6a — env vars must use `SCITEX_<PKG>_*`; bare `<PKG>_*` is forbidden.

    Scans the installed package's .py files. Best-effort: only flags
    obvious violations (bare-pkg prefix or non-allowed non-SCITEX vars).
    """
    expected = _expected_env_prefix(package)
    if expected is None:
        return
    bare = _bare_pkg_prefix(package)

    try:
        dist = im.distribution(package)
    except im.PackageNotFoundError:
        return
    files = dist.files or []
    py_files = [
        f
        for f in files
        if str(f).endswith(".py") and "/tests/" not in str(f) and "/test_" not in str(f)
    ]

    pat = re.compile(
        r"""os\.environ(?:\.get|\[)\s*\(?\s*["']([A-Z][A-Z0-9_]+)["']"""
        r"""|os\.getenv\s*\(\s*["']([A-Z][A-Z0-9_]+)["']"""
    )
    found_bare: set[str] = set()
    found_wrong: set[str] = set()
    for fp in py_files:
        try:
            text = Path(fp.locate()).read_text(encoding="utf-8", errors="ignore")
        except (OSError, AttributeError):
            continue
        for m in pat.finditer(text):
            var = m.group(1) or m.group(2)
            if not var or _is_allowed_env(var):
                continue
            if bare and var.startswith(bare):
                found_bare.add(var)
            elif var.startswith("SCITEX_") and not var.startswith(expected):
                # Cross-package reference (e.g. scitex-dev reading SCITEX_PLT_*).
                # Allow if the prefix matches a known sibling package; flag if it
                # doesn't (likely a typo).
                known_prefixes = _known_scitex_prefixes()
                matched = False
                for sibling in known_prefixes:
                    if var.startswith(sibling):
                        matched = True
                        break
                if not matched:
                    found_wrong.add(var)
            elif not var.startswith("SCITEX_") and not _is_allowed_env(var):
                found_wrong.add(var)

    for var in sorted(found_bare):
        out.append(
            Violation(
                package,
                "§6a",
                f"env var '{var}' uses bare package prefix — rename to '{expected}{var[len(bare or '') :]}'",
            )
        )
    for var in sorted(found_wrong):
        out.append(
            Violation(
                package,
                "§6a",
                f"env var '{var}' has no recognized prefix — use '{expected}*' or add to allowlist",
            )
        )


def _check_config_help(
    cmd: click.BaseCommand, package: str, out: list[Violation]
) -> None:
    """§6b — root --help must document the config-path fallback order."""
    expected = _expected_env_prefix(package)
    if expected is None:
        return
    text = " ".join(
        filter(None, [getattr(cmd, "help", "") or "", getattr(cmd, "epilog", "") or ""])
    )
    epilog_or_help = text.lower()
    has_config_yaml = "config.yaml" in epilog_or_help
    has_env_ref = f"{expected.lower()}config" in epilog_or_help or expected in text
    has_path_hint = ".scitex/" in epilog_or_help or "~/.scitex" in epilog_or_help
    if not (has_config_yaml or has_env_ref or has_path_hint):
        out.append(
            Violation(
                package,
                "§6b",
                f"root --help does not document config-path fallback "
                f"(expected mention of 'config.yaml', '{expected}CONFIG', or '~/.scitex/...')",
            )
        )


def _run_subprocess(args: list[str], timeout: float = 10.0) -> tuple[int, str, str]:
    """Run a CLI command; return (exit_code, stdout, stderr). -1 on timeout/error."""
    import subprocess

    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return -1, "", ""


def _collect_json_leaves(cmd: click.BaseCommand, path: list[str]) -> list[list[str]]:
    """Return paths (e.g. ['mcp', 'list-tools']) of every leaf that has --json."""
    out: list[list[str]] = []
    if getattr(cmd, "hidden", False):
        return out
    if isinstance(cmd, click.Group):
        for name, sub in cmd.commands.items():
            out.extend(_collect_json_leaves(sub, path + [name]))
        return out
    if "--json" in _flag_names(cmd):
        out.append(path)
    return out


def _collect_hidden_leaves(cmd: click.BaseCommand, path: list[str]) -> list[list[str]]:
    """Return paths of every hidden leaf (deprecation-redirect candidates)."""
    out: list[list[str]] = []
    if isinstance(cmd, click.Group):
        for name, sub in cmd.commands.items():
            child_path = path + [name]
            if getattr(sub, "hidden", False) and not isinstance(sub, click.Group):
                out.append(child_path)
            else:
                out.extend(_collect_hidden_leaves(sub, child_path))
    return out


def _check_behavioral(
    package: str,
    out: list[Violation],
    cmd: click.BaseCommand | None = None,
    timeout: float = 10.0,
) -> None:
    """Behavioral checks (§1a ladder, §3 exit codes, §5 redirects, §7 parity, §8 JSON)."""
    import json as _json

    sub_to = max(1.0, min(timeout, 30.0))

    # §3 — bogus flag at top level should exit 2 (Click default).
    rc, _so, _se = _run_subprocess(
        [package, "--definitely-not-a-flag-xyz"], timeout=sub_to
    )
    if rc != 2 and rc != -1:
        out.append(
            Violation(
                package,
                "§3",
                f"unknown flag at top-level exited {rc}, expected 2 (usage error)",
            )
        )

    # §3 — bogus subcommand should exit 2.
    rc, _so, _se = _run_subprocess(
        [package, "definitely-not-a-subcommand-xyz"], timeout=sub_to
    )
    if rc not in (
        2,
        -1,
        0,
    ):  # 0 means CLI accepted gibberish — also a bug, but separate signal
        if rc != 2:
            out.append(
                Violation(
                    package,
                    "§3",
                    f"unknown subcommand exited {rc}, expected 2 (usage error)",
                )
            )

    # §1a behavioral — list-python-apis verbosity ladder.
    levels = [[], ["-v"], ["-vv"], ["-vvv"]]
    counts: list[int] = []
    for extra in levels:
        rc, so, _se = _run_subprocess(
            [package, "list-python-apis", *extra], timeout=sub_to
        )
        if rc != 0:
            counts.append(-1)
            continue
        counts.append(len([ln for ln in so.splitlines() if ln.strip()]))
    if all(c >= 0 for c in counts):
        for i in range(1, len(counts)):
            if counts[i] < counts[i - 1]:
                out.append(
                    Violation(
                        f"{package} list-python-apis",
                        "§1a",
                        f"verbosity ladder not monotonic: -{'v' * i} produced fewer "
                        f"non-empty lines ({counts[i]}) than -{'v' * (i - 1)} ({counts[i - 1]})",
                    )
                )
                break

    # §8 — every leaf with --json must produce parseable JSON on stdout.
    if cmd is not None:
        for leaf_path in _collect_json_leaves(cmd, []):
            rc, so, _se = _run_subprocess(
                [package, *leaf_path, "--json"], timeout=sub_to
            )
            if rc == 0 and so.strip():
                try:
                    _json.loads(so)
                except _json.JSONDecodeError:
                    out.append(
                        Violation(
                            f"{package} {' '.join(leaf_path)}",
                            "§8",
                            "--json stdout is not parseable JSON (log contamination?)",
                        )
                    )

    # §5 — hidden leaves should be deprecation redirects: exit non-zero with
    # a "renamed" / "moved" message on stderr.
    if cmd is not None:
        for leaf_path in _collect_hidden_leaves(cmd, []):
            rc, _so, se = _run_subprocess([package, *leaf_path], timeout=sub_to)
            if rc == 0:
                out.append(
                    Violation(
                        f"{package} {' '.join(leaf_path)}",
                        "§5",
                        "hidden leaf exited 0 — expected non-zero deprecation redirect",
                    )
                )
                continue
            blob = se.lower()
            if not any(
                tok in blob for tok in ("renamed", "moved", "deprecated", "use ")
            ):
                out.append(
                    Violation(
                        f"{package} {' '.join(leaf_path)}",
                        "§5",
                        "hidden leaf exited non-zero but stderr lacks redirect hint "
                        "(expected 'renamed', 'moved', 'deprecated', or 'use ...')",
                    )
                )

    # §7 — CLI ↔ MCP parity. When both `list-python-apis --json` and
    # `mcp list-tools --json` are present, every Python API should map to
    # an MCP tool (loosely: the MCP set should cover a substantial fraction
    # of the Python API set).
    py_rc, py_so, _ = _run_subprocess(
        [package, "list-python-apis", "--json"], timeout=sub_to
    )
    mcp_rc, mcp_so, _ = _run_subprocess(
        [package, "mcp", "list-tools", "--json"], timeout=sub_to
    )
    if py_rc == 0 and mcp_rc == 0 and py_so.strip() and mcp_so.strip():
        try:
            py_set = _extract_names(_json.loads(py_so))
            mcp_set = _extract_names(_json.loads(mcp_so))
        except (_json.JSONDecodeError, AttributeError, TypeError):
            py_set, mcp_set = set(), set()
        if py_set and mcp_set:
            # MCP names typically prefix the package short name; strip it for comparison.
            short = package.replace("scitex-", "").replace("-", "_")
            mcp_normalized = {n.removeprefix(f"{short}_") for n in mcp_set}
            missing = py_set - mcp_normalized
            if missing and len(missing) > len(py_set) * 0.5:
                out.append(
                    Violation(
                        package,
                        "§7",
                        f"{len(missing)}/{len(py_set)} Python APIs have no matching MCP tool "
                        f"(sample: {sorted(missing)[:3]})",
                    )
                )


def _extract_names(payload) -> set[str]:
    """Pull a flat name set out of a JSON listing (handles list[str] | list[dict] | dict)."""
    if isinstance(payload, list):
        out: set[str] = set()
        for item in payload:
            if isinstance(item, str):
                out.add(item)
            elif isinstance(item, dict):
                for k in ("name", "tool", "api", "id"):
                    v = item.get(k)
                    if isinstance(v, str):
                        out.add(v)
                        break
        return out
    if isinstance(payload, dict):
        for k in ("apis", "tools", "items", "data", "results"):
            if k in payload:
                return _extract_names(payload[k])
        return set(k for k in payload.keys() if isinstance(k, str))
    return set()


def _ep_value_for(package: str) -> str | None:
    """First console-script `module:obj` value registered under `package`."""
    try:
        eps = im.entry_points(group="console_scripts")
    except TypeError:
        eps = im.entry_points().get("console_scripts", [])
    for ep in eps:
        if ep.name == package:
            return ep.value
    return None


# --------------------------------------------------------------------- #
# Rule severity & filtering                                              #
# --------------------------------------------------------------------- #

# Severity tiers — used by --severity to gate which findings are reported.
RULE_SEVERITY: dict[str, str] = {
    "§1": "error",
    "§1a": "error",
    "§1b": "error",
    "§1c": "info",
    "§1d": "warn",
    "§1e": "info",
    "§2": "warn",
    "§3": "warn",
    "§4": "warn",
    "§5": "error",
    "§6a": "warn",
    "§6b": "warn",
    "§7": "warn",
    "§8": "warn",
}
SEVERITY_ORDER = {"info": 0, "warn": 1, "error": 2}


def _filter_violations(
    violations: list[Violation],
    rules: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    min_severity: str | None = None,
) -> list[Violation]:
    """Apply --rule / --exclude / --severity gating to a violation list."""
    out: list[Violation] = []
    threshold = SEVERITY_ORDER.get(min_severity or "info", 0)
    rules_set = {r.lstrip("§") for r in rules}
    excl_set = {r.lstrip("§") for r in exclude}
    for v in violations:
        rule_key = v.rule.lstrip("§")
        if rules_set and rule_key not in rules_set:
            continue
        if rule_key in excl_set:
            continue
        sev = RULE_SEVERITY.get(v.rule, "warn")
        if SEVERITY_ORDER[sev] < threshold:
            continue
        out.append(v)
    return out


def _audit_one(
    package: str,
    behavioral: bool = False,
    timeout: float = 30.0,
) -> tuple[str, list[Violation]]:
    """Audit a single package; return (status, violations).

    Status is one of: "ok", "warn", "skip-mcp", "not-found", "not-auditable".
    """
    ep_value = _ep_value_for(package)
    if ep_value is None:
        return "not-found", []
    if _is_mcp_server_entry(ep_value):
        return "skip-mcp", []

    # MCP / argparse entry points may close stdio on import or write protocol
    # frames to stdout — `_isolated_streams` redirects the three standard
    # streams to /dev/null and restores them on exit.
    with _isolated_streams():
        cmd = _resolve_entry_point(package)

    if cmd is None:
        last_err = getattr(_resolve_entry_point, "_last_err", None)
        if hasattr(_resolve_entry_point, "_last_err"):
            delattr(_resolve_entry_point, "_last_err")
        return f"not-auditable: {last_err or 'unknown'}", []

    out: list[Violation] = []
    _walk(cmd, [], out, root_display=package)
    _check_introspection(cmd, package, out)
    _check_config_help(cmd, package, out)
    _scan_env_vars(package, out)
    if behavioral:
        _check_behavioral(package, out, cmd, timeout=timeout)
    return ("ok" if not out else "warn"), out


def _violation_to_dict(v: Violation) -> dict:
    return {"command": v.command, "rule": v.rule, "message": v.message}


def _emit_human(package: str, status: str, violations: list[Violation]) -> None:
    if status == "skip-mcp":
        click.echo(
            f"info  {package}: MCP / protocol server — skipped (use audit-mcp-tools when available)"
        )
        return
    if status == "not-found":
        click.echo(f"error {package}: no console script registered", err=True)
        return
    if status.startswith("not-auditable"):
        click.echo(f"error {package}: {status}", err=True)
        return
    if status == "ok":
        click.echo(f"ok    {package}: no CLI convention violations")
        return
    click.echo(f"warn  {package}: {len(violations)} warning(s)")
    for v in violations:
        click.echo(f"  [{v.rule}] {v.command}: {v.message}")


def _emit_json(records: list[dict], registry_provenance: str) -> None:
    import json as _json

    payload = {
        "registry_source": registry_provenance,
        "results": records,
    }
    click.echo(_json.dumps(payload, indent=2))


def run_audit(
    package: str,
    behavioral: bool = False,
    output_json: bool = False,
    registry_provenance: str = "",
    rules: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    min_severity: str | None = None,
    timeout: float = 30.0,
) -> int:
    """Audit a single package (single-target mode)."""
    status, violations = _audit_one(package, behavioral=behavioral, timeout=timeout)
    violations = _filter_violations(violations, rules, exclude, min_severity)
    if not violations and status == "warn":
        status = "ok"
    if output_json:
        rec = {
            "package": package,
            "status": status,
            "violations": [_violation_to_dict(v) for v in violations],
        }
        _emit_json([rec], registry_provenance or "single-package mode")
    else:
        _emit_human(package, status, violations)
    if status == "not-found" or status.startswith("not-auditable"):
        return 2
    return 0


def run_audit_all(
    behavioral: bool = False,
    output_json: bool = False,
    dry_run: bool = False,
    registry_path: str | Path | None = None,
    rules: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    min_severity: str | None = None,
    timeout: float = 30.0,
) -> int:
    """Audit every package in the registry (ecosystem-wide mode).

    With dry_run=True, lists the targets without auditing.
    """
    registry, provenance = _load_registry(registry_path)
    targets: list[tuple[str, str, str]] = []  # (name, ep_value, status_hint)
    for name, _info in registry.items():
        ep_value = _ep_value_for(name)
        if ep_value is None:
            targets.append((name, "", "not-found"))
            continue
        if _is_mcp_server_entry(ep_value):
            targets.append((name, ep_value, "skip-mcp"))
            continue
        targets.append((name, ep_value, "audit"))

    if dry_run:
        if output_json:
            payload = {
                "registry_source": provenance,
                "dry_run": True,
                "targets": [
                    {"package": n, "entry_point": ep, "action": s}
                    for n, ep, s in targets
                ],
            }
            import json as _json

            click.echo(_json.dumps(payload, indent=2))
        else:
            click.echo(f"# registry: {provenance}")
            click.echo(f"# {len(targets)} package(s) — dry-run, no audit performed")
            for name, ep, status in targets:
                click.echo(f"  {status:<12} {name:<28} {ep}")
        return 0

    records: list[dict] = []
    counts = {"ok": 0, "warn": 0, "skip-mcp": 0, "not-found": 0, "not-auditable": 0}
    for name, ep, hint in targets:
        if hint == "not-found":
            status, violations = "not-found", []
        elif hint == "skip-mcp":
            status, violations = "skip-mcp", []
        else:
            # Wall-clock watchdog so a single hanging package can't wedge --all.
            # Budget = behavioral subprocess cap + 5s slack for static checks.
            wall_budget = max(timeout + 5.0, 10.0)
            try:
                with _watchdog(wall_budget):
                    status, violations = _audit_one(
                        name, behavioral=behavioral, timeout=timeout
                    )
            except _PackageTimeout:
                status, violations = (
                    f"not-auditable: timed out after {wall_budget:.0f}s",
                    [],
                )
        violations = _filter_violations(violations, rules, exclude, min_severity)
        if not violations and status == "warn":
            status = "ok"
        if not output_json:
            _emit_human(name, status, violations)
        records.append(
            {
                "package": name,
                "status": status,
                "violations": [_violation_to_dict(v) for v in violations],
            }
        )
        bucket = "not-auditable" if status.startswith("not-auditable") else status
        counts[bucket] = counts.get(bucket, 0) + 1

    if output_json:
        _emit_json(records, provenance)
    else:
        click.echo("")
        click.echo(f"# registry: {provenance}")
        click.echo(
            f"# summary: {counts['ok']} ok, {counts['warn']} warn, "
            f"{counts['skip-mcp']} skipped (MCP), "
            f"{counts['not-found']} not-found, {counts['not-auditable']} not-auditable"
        )
    return 0
