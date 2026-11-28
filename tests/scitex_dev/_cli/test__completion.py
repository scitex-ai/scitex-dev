"""Shell-completion install: drop-in files only, never an rc edit (scitex-dev#1127).

Every test runs the real CLI against a real temporary HOME; git work trees
are created with the real `git` binary.
"""

import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner
from scitex_dev._cli import main

_RC_TEXT = "# user rc\nexport KEEP=1\n"


def _env(home: Path, **extra) -> dict:
    """An isolated environment: only HOME decides where files go."""
    env = {
        "HOME": str(home),
        "XDG_DATA_HOME": None,
        "XDG_CONFIG_HOME": None,
        "BASH_COMPLETION_USER_DIR": None,
        "SCITEX_DIR": None,
    }
    env.update(extra)
    return env


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bashrc").write_text(_RC_TEXT)
    (home / ".zshrc").write_text(_RC_TEXT)
    return home


def _install(home: Path, *args, **extra_env):
    return CliRunner().invoke(
        main,
        ["install-shell-completion", "--yes", *args],
        env=_env(home, **extra_env),
    )


def _bash_dropin(home: Path) -> Path:
    return home / ".local/share/bash-completion/completions/scitex-dev"


def _git_init(path: Path) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_completion_uses_current_click_without_running_path_executable(tmp_path, shell):
    # Arrange
    marker = tmp_path / "foreign-executable-ran"
    foreign = tmp_path / "scitex-dev"
    foreign.write_text(
        f"#!/bin/sh\nprintf foreign > '{marker}'\nprintf FOREIGN_SCRIPT\n"
    )
    foreign.chmod(0o700)
    # Act
    result = CliRunner().invoke(
        main, ["print-shell-completion", "--shell", shell], env={"PATH": str(tmp_path)}
    )
    # Assert
    assert (
        result.exit_code,
        "_SCITEX_DEV_COMPLETE" in result.stdout,
        "FOREIGN_SCRIPT" in result.stdout,
        marker.exists(),
    ) == (0, True, False, False)


def test_completion_is_available_without_installed_executables_on_path(tmp_path):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(
        main, ["print-shell-completion", "--shell", "bash"], env={"PATH": str(tmp_path)}
    )
    # Assert
    assert (
        result.exit_code,
        "_SCITEX_DEV_COMPLETE=bash_complete" in result.stdout,
    ) == (0, True)


def test_bash_install_writes_dropin_and_leaves_rc_untouched(tmp_path):
    # Arrange
    home = _home(tmp_path)
    # Act
    result = _install(home)
    # Assert
    assert (
        result.exit_code,
        "_SCITEX_DEV_COMPLETE=bash_complete" in _bash_dropin(home).read_text(),
        (home / ".bashrc").read_text(),
        sorted(p.name for p in home.iterdir()),
    ) == (0, True, _RC_TEXT, [".bashrc", ".local", ".zshrc"])


def test_second_install_is_a_no_op(tmp_path):
    # Arrange
    home = _home(tmp_path)
    _install(home)
    before = _bash_dropin(home).stat()
    # Act
    result = _install(home)
    after = _bash_dropin(home).stat()
    # Assert
    assert (
        result.exit_code,
        "Up to date" in result.stdout,
        (before.st_ino, before.st_mtime_ns),
    ) == (0, True, (after.st_ino, after.st_mtime_ns))


def test_dry_run_writes_nothing(tmp_path):
    # Arrange
    home = _home(tmp_path)
    # Act
    result = _install(home, "--dry-run")
    # Assert
    assert (
        result.exit_code,
        str(_bash_dropin(home)) in result.stdout,
        (home / ".local").exists(),
    ) == (0, True, False)


def test_zsh_and_fish_dropins_honour_xdg_dirs(tmp_path):
    # Arrange
    home = _home(tmp_path)
    data, config = tmp_path / "data", tmp_path / "config"
    xdg = {"XDG_DATA_HOME": str(data), "XDG_CONFIG_HOME": str(config)}
    # Act
    zsh = _install(home, "--shell", "zsh", **xdg)
    fish = _install(home, "--shell", "fish", **xdg)
    # Assert
    assert (
        zsh.exit_code,
        fish.exit_code,
        (data / "zsh/site-functions/_scitex-dev").read_text().startswith("#compdef"),
        (config / "fish/completions/scitex-dev.fish").is_file(),
        (home / ".zshrc").read_text(),
    ) == (0, 0, True, True, _RC_TEXT)


def test_bash_completion_user_dir_is_honoured(tmp_path):
    # Arrange
    home = _home(tmp_path)
    user_dir = tmp_path / "bc-user"
    # Act
    result = _install(home, BASH_COMPLETION_USER_DIR=f"{user_dir}:/elsewhere")
    # Assert
    assert (result.exit_code, (user_dir / "completions/scitex-dev").is_file()) == (
        0,
        True,
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="requires real git")
def test_refuses_when_completion_dir_links_into_a_git_work_tree(tmp_path):
    # Arrange — a dotfiles checkout manages ~/.local/share/bash-completion
    home = _home(tmp_path)
    dotfiles = tmp_path / "dotfiles"
    _git_init(dotfiles)
    (dotfiles / "bash-completion").mkdir()
    (home / ".local/share").mkdir(parents=True)
    (home / ".local/share/bash-completion").symlink_to(dotfiles / "bash-completion")
    # Act
    result = _install(home)
    status = subprocess.run(
        ["git", "-C", str(dotfiles), "status", "--porcelain", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    )
    # Assert
    assert (
        result.exit_code,
        "git work tree" in result.output,
        status.stdout,
    ) == (1, True, "")


@pytest.mark.skipif(shutil.which("git") is None, reason="requires real git")
def test_refuses_to_replace_a_symlink_into_a_git_work_tree(tmp_path):
    # Arrange — the drop-in slot itself is a dotfiles-managed symlink
    home = _home(tmp_path)
    dotfiles = tmp_path / "dotfiles"
    _git_init(dotfiles)
    managed = dotfiles / "scitex-dev.bash"
    managed.write_text("# managed by dotfiles\n")
    _bash_dropin(home).parent.mkdir(parents=True)
    _bash_dropin(home).symlink_to(managed)
    # Act
    result = _install(home)
    # Assert
    assert (
        result.exit_code,
        _bash_dropin(home).is_symlink(),
        managed.read_text(),
    ) == (1, True, "# managed by dotfiles\n")


def test_replaces_legacy_symlink_with_a_real_file(tmp_path):
    # Arrange — older installs symlinked the slot to a ~/.scitex cache file
    home = _home(tmp_path)
    cache = home / ".scitex/dev/runtime/completion/scitex-dev"
    cache.parent.mkdir(parents=True)
    cache.write_text("# legacy cache\n")
    _bash_dropin(home).parent.mkdir(parents=True)
    _bash_dropin(home).symlink_to(cache)
    # Act
    result = _install(home)
    # Assert
    assert (
        result.exit_code,
        _bash_dropin(home).is_symlink(),
        cache.read_text(),
        "_SCITEX_DEV_COMPLETE" in _bash_dropin(home).read_text(),
    ) == (0, False, "# legacy cache\n", True)


def test_legacy_rc_line_is_reported_but_not_edited(tmp_path):
    # Arrange
    home = _home(tmp_path)
    legacy = (
        "[ -f /x/.scitex/dev/runtime/completion/scitex-dev ] && source "
        "/x/.scitex/dev/runtime/completion/scitex-dev  # scitex-dev tab completion"
    )
    rc_text = _RC_TEXT + legacy + "\n"
    (home / ".bashrc").write_text(rc_text)
    # Act
    result = _install(home)
    # Assert
    assert (
        result.exit_code,
        legacy in result.output,
        (home / ".bashrc").read_text(),
    ) == (0, True, rc_text)


def test_legacy_marker_on_its_own_line_reports_the_following_eval_line(tmp_path):
    # Arrange — the umbrella CLI's old two-line block
    home = _home(tmp_path)
    eval_line = 'eval "$(_SCITEX_DEV_COMPLETE=bash_source /usr/bin/scitex-dev)"'
    rc_text = _RC_TEXT + "# scitex-dev tab completion\n" + eval_line + "\n"
    (home / ".bashrc").write_text(rc_text)
    # Act
    result = _install(home)
    # Assert
    assert (eval_line in result.output, (home / ".bashrc").read_text()) == (
        True,
        rc_text,
    )


def test_aliases_get_one_dropin_each(tmp_path):
    # Arrange
    import click
    from scitex_dev._cli._completion import attach_shell_completion

    @click.group()
    def demo():
        """Demo group."""

    attach_shell_completion(demo, prog_name="scitex-demo", aliases=("sdemo",))
    home = _home(tmp_path)
    completions = home / ".local/share/bash-completion/completions"
    # Act
    result = CliRunner().invoke(
        demo, ["install-shell-completion", "--yes"], env=_env(home)
    )
    # Assert
    assert (
        result.exit_code,
        "_SCITEX_DEMO_COMPLETE" in (completions / "scitex-demo").read_text(),
        "_SDEMO_COMPLETE" in (completions / "sdemo").read_text(),
    ) == (0, True, True)


@pytest.mark.skipif(shutil.which("bash") is None, reason="requires real Bash")
def test_installed_dropin_can_be_sourced_with_spaces_and_quotes_in_home(tmp_path):
    # Arrange
    home = tmp_path / "owned home's dir"
    home.mkdir()
    # Act
    install = _install(home)
    loaded = subprocess.run(
        [
            shutil.which("bash"),
            "--noprofile",
            "--norc",
            "-c",
            'source "$1" && declare -F _scitex_dev_completion',
            "owned-check",
            str(_bash_dropin(home)),
        ],
        env={"PATH": "/usr/bin:/bin", "HOME": str(home)},
        check=False,
        capture_output=True,
        text=True,
    )
    # Assert
    assert (install.exit_code, loaded.returncode, loaded.stdout.strip()) == (
        0,
        0,
        "_scitex_dev_completion",
    )


_BASH_COMPLETION = Path("/usr/share/bash-completion/bash_completion")


@pytest.mark.skipif(
    shutil.which("bash") is None or not _BASH_COMPLETION.is_file(),
    reason="requires Bash with bash-completion installed",
)
def test_bash_completion_lazy_loads_the_dropin_without_any_rc_line(tmp_path):
    # Arrange
    home = _home(tmp_path)
    _install(home)
    probe = (
        f'source "{_BASH_COMPLETION}"; '
        "if declare -F _comp_load >/dev/null; then _comp_load scitex-dev; "
        "else __load_completion scitex-dev; fi; complete -p scitex-dev"
    )
    # Act
    loaded = subprocess.run(
        [shutil.which("bash"), "--noprofile", "--norc", "-c", probe],
        env={"PATH": "/usr/bin:/bin", "HOME": str(home)},
        check=False,
        capture_output=True,
        text=True,
    )
    # Assert
    assert (loaded.returncode, "_scitex_dev_completion" in loaded.stdout) == (0, True)


def test_public_cli_module_exports_the_completion_building_blocks():
    # Arrange
    import scitex_dev.cli as public
    from scitex_dev._cli import _completion

    names = (
        "attach_shell_completion",
        "completion_dropin_path",
        "generate_completion_script",
        "install_completion",
        "legacy_rc_lines",
    )
    # Act
    resolved = [getattr(public, n) is getattr(_completion, n) for n in names]
    # Assert
    assert resolved == [True] * len(names)


def test_ecosystem_install_does_not_wire_completions_by_default():
    # Arrange
    ctx = main.make_context("scitex-dev", ["ecosystem"], resilient_parsing=True)
    ecosystem = main.get_command(ctx, "ecosystem")
    install = ecosystem.get_command(ctx, "install")
    # Act
    option = next(p for p in install.params if p.name == "with_completions")
    # Assert
    assert option.default is False
