"""Surgical repair of a PS-140 gate's hand-owned tail.

WHY THIS EXISTS. The generated gate file has two halves: the import list
between the sentinels, which `install-cross-package-gate` owns and rewrites,
and everything below the closing sentinel, which it deliberately preserves
byte-identically so a leaf that hand-strengthened its assertion is not
silently reverted. That policy is correct and it has a cost: **the PS-140
defect lives in the preserved half.**

Measured 2026-08-23 against the remotes: 25 of 76 org repositories carry, on
`develop`, a tail that guards with

    module = pytest.importorskip(module_name)      # the FULL dotted path

which SKIPS when a submodule is missing, so a rename inside an installed peer
reports as an absence and the run reads green. The gate exists to catch that
and cannot. Regenerating does not help — a `--dry-run` re-emits the broken
body verbatim, by design — so the rule reported an error and named no runnable
remedy for an existing file. That is the defect this module removes.

WHAT IT DOES **NOT** DO. It does not replace the tail with a canned body.
Two shapes are in the fleet and only one is stock:

    scitex-logging / scitex-str  (stock)
        module = pytest.importorskip(name)
        assert module is not None

    scitex-io                    (hand-strengthened, and still broken)
        mod = pytest.importorskip(module_name)
        assert getattr(mod, "__name__", None) == module_name

scitex-io is exactly the case the no-touch policy protects, and swapping in a
canned body would throw its stronger assertion away. So the repair is
SURGICAL: it rewrites the GUARD and leaves everything downstream — the binding
name, the assertion, the docstring, any extra tests — untouched. Someone
improved that gate and the improvement could not reach the defect, because the
defect is in the guard, not the assertion; the repair therefore edits only the
guard.

WHEN IT DECLINES. If the shape cannot be PROVEN from the AST, nothing is
written and the caller is told which file and why. A repair that guesses is
worse than an error message: a wrong rewrite of a test gate is invisible
exactly the way the original defect is.
"""

from __future__ import annotations

import ast
from typing import NamedTuple

__all__ = ["TailRepair", "repair_tail"]


class TailRepair(NamedTuple):
    """Outcome of attempting to repair one tail.

    `changed` is False both when the tail is already correct and when the
    repair declined — `reason` distinguishes them, and callers must print it.
    Collapsing "already fine" into "could not fix" is how a sweep reports
    success over files it never touched.
    """

    changed: bool
    tail: str
    reason: str


#: The parameter name the generated gate parametrizes over. A tail that
#: parametrizes over something else is not a shape this module claims to
#: understand, and it declines rather than guessing.
_PARAM = "module_name"


def _find_guard(tree: ast.Module) -> tuple[ast.Assign, ast.Call, str] | None:
    """Locate `<target> = pytest.importorskip(<name>)` in a parametrized test.

    Returns (assignment, call, argument-name) or None. The argument name is
    returned rather than assumed so the caller can check it actually refers to
    the parametrized module name, directly or through one alias hop.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if not isinstance(func, ast.Attribute) or func.attr != "importorskip":
            continue
        if not isinstance(func.value, ast.Name) or func.value.id != "pytest":
            continue
        if len(call.args) != 1 or not isinstance(call.args[0], ast.Name):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        return node, call, call.args[0].id
    return None


def _find_alias(tree: ast.Module, alias: str) -> ast.Assign | None:
    """Locate a bare `<alias> = module_name` assignment, if there is one.

    The stock body binds the parameter to a local first (`name = module_name`)
    and guards on the local. After the repair the local is unused, and an
    unused local is a lint failure, so the assignment has to go with it.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if node.targets[0].id != alias:
            continue
        if isinstance(node.value, ast.Name) and node.value.id == _PARAM:
            return node
    return None


def _uses(tree: ast.Module, name: str, *, excluding: set[int]) -> bool:
    """True if `name` is LOADED anywhere outside the excluded line numbers."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name:
            if isinstance(node.ctx, ast.Load) and node.lineno not in excluding:
                return True
    return False


def repair_tail(tail: str) -> TailRepair:
    """Rewrite a full-path `importorskip` guard into the root-split form.

    The replacement is PS-140's own advice, and the two-statement shape is
    deliberate: the intermediate binding is what makes the root/full-path
    distinction visible to a reader.

        root = module_name.split(".")[0]
        pytest.importorskip(root)
        <original target> = importlib.import_module(module_name)

    Everything after the guard is preserved, which is what keeps a
    hand-strengthened assertion (scitex-io) intact.
    """
    if "importlib.import_module" in tail and "importorskip" in tail:
        return TailRepair(False, tail, "already guards on the root")

    try:
        tree = ast.parse(tail.replace("# ===== END AUTO-GENERATED =====", "", 1))
    except SyntaxError as exc:
        return TailRepair(False, tail, f"tail does not parse ({exc})")

    found = _find_guard(tree)
    if found is None:
        return TailRepair(
            False,
            tail,
            "no `<target> = pytest.importorskip(<name>)` assignment found — "
            "this tail is not a shape this repair understands",
        )
    assign, _call, arg = found

    alias_node = None
    if arg != _PARAM:
        alias_node = _find_alias(tree, arg)
        if alias_node is None:
            return TailRepair(
                False,
                tail,
                f"the guard skips on `{arg}`, which is not `{_PARAM}` and is "
                "not a single alias of it — refusing to guess what it holds",
            )

    target = assign.targets[0].id  # type: ignore[union-attr]

    # Line numbers come from the SENTINEL-STRIPPED parse, and the sentinel is
    # replaced by an empty string of the same line count (it is one line, and
    # `replace` leaves the newline), so numbering matches the original tail.
    lines = tail.splitlines(keepends=True)
    guard_index = assign.lineno - 1
    if guard_index >= len(lines):  # pragma: no cover - defensive
        return TailRepair(False, tail, "line numbering did not match the tail")

    indent = lines[guard_index][
        : len(lines[guard_index]) - len(lines[guard_index].lstrip())
    ]
    skip_guard = (
        f'{indent}root = {_PARAM}.split(".")[0]\n'
        f"{indent}pytest.importorskip(root)\n"
    )
    real_import = f"{indent}{target} = importlib.import_module({_PARAM})\n"

    alias_index = None
    if alias_node is not None and not _uses(
        tree, arg, excluding={assign.lineno, alias_node.lineno}
    ):
        alias_index = alias_node.lineno - 1

    if alias_index is None:
        # No alias to reclaim: everything goes where the old guard was.
        lines[guard_index] = skip_guard + real_import
    else:
        # THE SKIP GOES WHERE THE ALIAS WAS, and that placement is not
        # cosmetic. The stock body binds `name = module_name` under
        # `# Arrange` and guards under `# Act`; the skip is a PRECONDITION,
        # so it belongs in Arrange, and the real import is the act. Putting
        # both at the guard site would leave an empty Arrange section --
        # legal under STX-TQ002, which only checks that the three markers
        # appear in order, and misleading to every human who reads it.
        lines[alias_index] = skip_guard
        lines[guard_index] = real_import

    return TailRepair(
        True,
        "".join(lines),
        f"guard rewritten to skip on the root; `{target}` now bound by "
        "importlib.import_module on the full path",
    )
