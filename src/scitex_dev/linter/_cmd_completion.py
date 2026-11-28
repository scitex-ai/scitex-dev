"""Static completion script text for the linter's `show-completion-*` leaves.

Installing completion is the shared helper's job
(`scitex_dev._cli._completion`); nothing here writes to the filesystem.
The argparse-era `completion install` that appended to ~/.bashrc was removed
(scitex-dev#1127).
"""


def _generate_completion_script(shell: str) -> str:
    """Generate a static completion script for scitex-linter."""
    if shell == "bash":
        return """# scitex-linter tab completion (bash)
_scitex_linter_complete() {
    local cur prev cmds
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    cmds="check format python rule rules list-python-apis api mcp completion"

    case "$prev" in
        scitex-linter)
            COMPREPLY=( $(compgen -W "$cmds --help --help-recursive --version" -- "$cur") )
            return 0
            ;;
        check)
            COMPREPLY=( $(compgen -W "--json --no-color --severity --category --help" -f -- "$cur") )
            return 0
            ;;
        format)
            COMPREPLY=( $(compgen -W "--check --diff --help" -f -- "$cur") )
            return 0
            ;;
        python)
            COMPREPLY=( $(compgen -W "--strict --help" -f -- "$cur") )
            return 0
            ;;
        rule|rules)
            COMPREPLY=( $(compgen -W "--json --category --severity --help" -- "$cur") )
            return 0
            ;;
        list-python-apis|api)
            COMPREPLY=( $(compgen -W "--json -v --verbose --help" -- "$cur") )
            return 0
            ;;
        mcp)
            COMPREPLY=( $(compgen -W "start list-tools doctor installation --help" -- "$cur") )
            return 0
            ;;
        completion)
            COMPREPLY=( $(compgen -W "install status bash zsh --help" -- "$cur") )
            return 0
            ;;
        --severity)
            COMPREPLY=( $(compgen -W "error warning info" -- "$cur") )
            return 0
            ;;
    esac

    COMPREPLY=( $(compgen -f -- "$cur") )
}
complete -F _scitex_linter_complete scitex-linter"""
    elif shell == "zsh":
        return """# scitex-linter tab completion (zsh)
#compdef scitex-linter

_scitex-linter() {
    local -a commands
    commands=(
        'check:Check Python files for SciTeX pattern compliance'
        'format:Auto-fix SciTeX pattern issues'
        'python:Lint then execute a Python script'
        'rule:List all lint rules'
        'rules:List all lint rules (built-in + plugin)'
        'list-python-apis:List public Python API'
        'api:List public Python API'
        'mcp:MCP server commands'
        'completion:Shell tab completion'
    )

    _arguments -C \\
        '(-h --help)'{-h,--help}'[Show help]' \\
        '(-V --version)'{-V,--version}'[Show version]' \\
        '--help-recursive[Show help for all commands]' \\
        '1:command:->cmd' \\
        '*::arg:->args'

    case $state in
        cmd)
            _describe 'command' commands
            ;;
    esac
}

_scitex-linter "$@" """
    return ""
