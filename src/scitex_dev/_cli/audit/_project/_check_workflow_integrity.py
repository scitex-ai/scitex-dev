"""Detect literal profile-changing install fallbacks and protection bypasses.

This is a local workflow check, not a general shell interpreter. Indirect or
external scripts still require their own source review and behavioral tests.
"""

from pathlib import Path
import re
import shlex

import yaml

WORKFLOW_INTEGRITY_RULES = (
    (
        "PS-235",
        "§3",
        "Workflow installs must not change local test profiles after failure.",
        "E",
        "workflow-install-profile-fallback",
    ),
    (
        "PS-236",
        "§3",
        "Workflow merges must preserve branch protection.",
        "E",
        "workflow-protection-bypass",
    ),
)


def _lex(line):
    """Keep quoted operators as arguments and compound assignments together."""
    quoted = {}
    prefix = "_SCITEX_WORKFLOW_QUOTE_"
    while prefix in line:
        prefix += "_"

    def protect(match):
        marker = f"{prefix}{len(quoted)}_"
        quoted[marker] = shlex.split(match.group())[0]
        return marker

    masked = re.sub(r"""(?<!\\)(?:'[^']*'|"(?:\\.|[^"\\])*")""", protect, line)
    lexer = shlex.shlex(masked, posix=True, punctuation_chars=";&|<")
    lexer.whitespace_split = True
    lexer.commenters = "#"
    return list(lexer), quoted


def _words(tokens, quoted):
    words = []
    for token in tokens:
        for marker, value in quoted.items():
            token = token.replace(marker, value)
        words.append(token)
    return words


def _head(words):
    words = list(words)
    while words and (
        words[0] in {"if", "then", "do", "!", "command", "exec", "env"}
        or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0])
    ):
        words.pop(0)
    return words


def _profile(words):
    words = _head(words)
    if not words:
        return None
    binary = Path(words[0]).name
    if binary == "uv" and words[1:3] == ["pip", "install"]:
        arguments = words[3:]
    elif binary in {"pip", "pip3"} and words[1:2] == ["install"]:
        arguments = words[2:]
    elif binary.startswith("python") and words[1:4] == ["-m", "pip", "install"]:
        arguments = words[4:]
    else:
        return None
    targets = []
    for index, argument in enumerate(arguments):
        if argument in {"-e", "--editable"} and index + 1 < len(arguments):
            targets.append(arguments[index + 1])
        elif argument.startswith("--editable="):
            targets.append(argument.split("=", 1)[1])
        elif argument.startswith("-e") and len(argument) > 2:
            targets.append(argument[2:])
    for argument in targets or arguments:
        match = re.fullmatch(r"\.(?:\[([A-Za-z0-9_,. -]+)\])?", argument)
        if match:
            return frozenset(
                re.sub(r"[-_.]+", "-", name.strip().lower())
                for name in (match.group(1) or "").split(",")
                if name.strip()
            )
    return None


def _commands(script):
    """Yield command segments and their following operator; skip heredoc data."""
    pending, first, heredoc = "", 1, None
    for number, raw in enumerate(script.splitlines(), 1):
        if heredoc:
            if raw.strip() == heredoc:
                heredoc = None
            continue
        if not pending:
            first = number
        if raw.rstrip().endswith("\\"):
            pending += raw.rstrip()[:-1] + " "
            continue
        line, pending = pending + raw, ""
        try:
            tokens, quoted = _lex(line)
        except ValueError:
            # Parse the entire quoted fragment before recognizing commands.
            pending = line + "\n"
            continue
        for index, token in enumerate(tokens[:-1]):
            if token == "<<":
                delimiter = _words([tokens[index + 1]], quoted)[0].lstrip("-")
                if re.fullmatch(r"[A-Za-z_]\w*", delimiter):
                    heredoc = delimiter
        command = []
        for token in tokens:
            if token in {";", "&&", "||", "|"}:
                yield first, _head(_words(command, quoted)), token
                command = []
            else:
                command.append(token)
        if command:
            yield first, _head(_words(command, quoted)), None


def _inspect(script):
    previous, operator = None, None
    for number, words, following in _commands(script):
        target = _profile(words)
        if (
            operator == "||"
            and previous is not None
            and target is not None
            and previous != target
        ):
            yield "PS-235", number, "An install failure selects another local extras profile; require one explicit profile and stop on failure."
        if (
            len(words) >= 3
            and Path(words[0]).name == "gh"
            and words[1:3] == ["pr", "merge"]
            and "--admin" in words[3:]
        ):
            yield "PS-236", number, "gh pr merge --admin bypasses branch protection; leave the PR open until normal checks and reviews permit merging."
        previous, operator = target, following


def _default_shell(mapping, fallback):
    defaults = mapping.get("defaults", {})
    run = defaults.get("run", {}) if isinstance(defaults, dict) else {}
    return run.get("shell", fallback) if isinstance(run, dict) else fallback


def check_workflow_integrity(repo_root, violation_cls, out):
    """Append known unsafe literal shell patterns from active workflow files."""
    directory = Path(repo_root) / ".github/workflows"
    files = sorted({*directory.glob("*.yml"), *directory.glob("*.yaml")})
    for path in files:
        relative = str(path.relative_to(repo_root))
        try:
            data = yaml.safe_load(path.read_text())
        except (OSError, UnicodeError, yaml.YAMLError) as error:
            out.append(
                violation_cls(
                    "PS-235",
                    relative,
                    f"Cannot inspect workflow YAML ({type(error).__name__}).",
                )
            )
            continue
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), dict):
            continue
        for job_name, job in data["jobs"].items():
            if not isinstance(job, dict):
                continue
            default_shell = _default_shell(job, _default_shell(data, "bash"))
            for index, step in enumerate(job.get("steps", [])):
                if not isinstance(step, dict) or not isinstance(step.get("run"), str):
                    continue
                shell = str(step.get("shell", default_shell)).split()
                if not shell or Path(shell[0]).name not in {"bash", "sh"}:
                    continue
                for code, line, detail in _inspect(step["run"]):
                    out.append(
                        violation_cls(
                            code,
                            f"{relative}::{job_name}::step[{index}]:{line}",
                            detail,
                        )
                    )
