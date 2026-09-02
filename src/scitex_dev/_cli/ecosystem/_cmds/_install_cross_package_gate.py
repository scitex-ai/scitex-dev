#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `install-cross-package-gate` — materialise the PS-140 gate.

PS-140 requires any package with cross-package imports to ship
`tests/integration/test_cross_package_imports.py` declaring every
cross-package module name. The rule has DETECTED that gap since it was
written, but its remediation text pointed at
`python /tmp/write-integration-tests.py <pkg-dir>` — a path in a
world-writable directory, shipped nowhere, hedged in the rule text
itself with "(or the equivalent scitex-dev subcommand)". No such
subcommand existed. Reported by scitex-hpc, 2026-07-29, who hit the
remediation, found nothing to run, and hand-edited a block whose own
header says it is auto-generated.

A check that can detect but not remediate pushes a careful reader into
doing by hand the thing the file warns against. That is the check's
defect, not the reader's.

SSoT: the expected-import set is computed by importing
:func:`_collect_cross_package_imports` FROM the PS-140 checker — the
same function the audit grades against. The previous arrangement had
the checker's docstring promise to "mirror" the /tmp script; two
implementations of one fact drift silently, and this one drifted all
the way to nonexistence. Generator and gate now cannot disagree,
because there is only one of them.
"""

import subprocess
from pathlib import Path

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand
from ...audit._project._check_umbrella_dep_and_integration import (
    _collect_cross_package_imports,
    _own_import_name,
)
from ._gate_sentinel import BEGIN_SENTINEL, END_SENTINEL, split_at_sentinel
from ._write_target import assert_target_is_distribution, resolve_write_target


#: What sits below the closing sentinel when there is no existing tail to
#: preserve. The parametrized test lives HERE, not in the generated head,
#: and that placement is the whole point: the 2026-07-29 population put it
#: below the sentinel, scitex-io then deliberately STRENGTHENED its
#: assertion in place, and a regenerator that owned this region would have
#: silently reverted that. The generated region is the import LIST and
#: nothing else.
DEFAULT_GATE_TAIL = (
    END_SENTINEL + "\n"
    "\n"
    "\n"
    '@pytest.mark.parametrize("module_name", CROSS_PACKAGE_IMPORTS)\n'
    "def test_cross_package_import_resolves(module_name):\n"
    "    # Arrange \u2014 skip on the ROOT, and only on the ROOT. PS-140's own\n"
    "    # prose: banning the skip outright \"would convert a legitimate\n"
    "    # absence into a hard failure \u2014 a gate that cannot PASS, in place\n"
    "    # of one that cannot FAIL.\" A lean install where a peer\n"
    "    # distribution is genuinely absent must SKIP here, not fail.\n"
    "    #\n"
    "    # Two statements ON PURPOSE. The intermediate binding is what\n"
    "    # makes the root/full-path distinction visible to a reader, which\n"
    "    # is the entire point of the shape; inlining it to satisfy a\n"
    "    # checker would make this file harder to read.\n"
    "    root = module_name.split(\".\")[0]\n"
    "    pytest.importorskip(root)\n"
    "\n"
    "    # Act \u2014 a real import of the FULL dotted path. Not\n"
    "    # importlib.util.find_spec, which only proves a module is\n"
    "    # FINDABLE while the failures this gate exists to catch (a\n"
    "    # renamed symbol re-exported through a package __init__) happen\n"
    "    # at EXECUTION. And not importorskip(module_name), which skips on\n"
    "    # the full path and so reports the rename as an absence.\n"
    "    module = importlib.import_module(module_name)\n"
    "\n"
    "    # Assert\n"
    "    assert module is not None\n"
)


def render_cross_package_gate(
    distribution: str, imports: list[str], tail: str | None = None
) -> str:
    """Source of the generated `test_cross_package_imports.py`.

    `imports` is rendered as the `CROSS_PACKAGE_IMPORTS` list literal
    that PS-140's `_read_declared_imports` parses back out via AST, so
    the emitted shape is the one the auditor can actually read (a plain
    `Assign` of a `List` of string `Constant`s — not an f-string, a
    comprehension, or a tuple).

    `tail` is everything from the closing sentinel onward, and it is a
    PARAMETER rather than a constant because regeneration must be able to
    hand back the bytes it found. It already begins with END_SENTINEL (that
    is what :func:`split_at_sentinel` returns), so it is concatenated
    directly. None means "no existing file to preserve" and yields
    :data:`DEFAULT_GATE_TAIL`.

    The sentinel pair is emitted around the list and NOWHERE else. Before
    this, the renderer emitted no sentinels at all while the deployed
    population carried them and invited hand-written cases below the
    second one — so regenerating did not merely fail to preserve the tail,
    it removed the only defined home for one.
    """
    listed = "\n".join(f"    {name!r}," for name in sorted(imports))
    from scitex_dev import __version__ as _gen_version

    return (
        '"""Cross-package import gate (PS-140) for ' + distribution + ".\n"
        "\n"
        "Every module listed here is imported by this package's source but\n"
        "OWNED by a peer standalone. A rename or move on the other side of\n"
        "that boundary is invisible to this package's unit tests and\n"
        "surfaces as ModuleNotFoundError in a user's process — which is how\n"
        "the `scitex_io._load_cache` rename went undetected for weeks.\n"
        "\n"
        "Generated by `scitex-dev ecosystem install-cross-package-gate`.\n"
        "\n"
        f"generated-by: scitex-dev {_gen_version}\n"
        "\n"
        "A GATE NOBODY CAN DATE IS A CLAIM ABOUT AN UNKNOWN PAST. This\n"
        "list is a snapshot of the cross-package imports as they stood\n"
        "when the stamp above was written; it does not update itself, and\n"
        "a stale copy looks exactly like a current one. Measured\n"
        "2026-08-16: 17 gates across the fleet carried NO stamp and named\n"
        "a generator that never existed as a command -- the real writer\n"
        "was a one-shot script since deleted -- so the only way to tell a\n"
        "fossil from a live gate was a filesystem sweep of mtimes. The\n"
        "same disease had already been found in the audit gate (68 of 70\n"
        "still calling audit_all_for_package() with no path=), and the\n"
        "same cure applies: say which version wrote you.\n"
        "\n"
        "Regenerate with:\n"
        "\n"
        "    scitex-dev ecosystem install-cross-package-gate "
        + distribution
        + " --force\n"
        "\n"
        "Do not hand-edit the list: the PS-140 auditor recomputes it from\n"
        "source on every run and fails on any drift in either direction\n"
        "(a missing entry OR a stale one).\n"
        "\n"
        "Hand-written cases go BELOW the second sentinel. Everything there\n"
        "is preserved byte-identically across regeneration; everything\n"
        "between the sentinels is overwritten.\n"
        '"""\n'
        "\n"
        "import importlib\n"
        "\n"
        "import pytest\n"
        "\n" + BEGIN_SENTINEL + "\n"
        "CROSS_PACKAGE_IMPORTS = [\n" + listed + "\n"
        "]\n" + (DEFAULT_GATE_TAIL if tail is None else tail)
    )


def register(ecosystem):
    @ecosystem.command(
        "install-cross-package-gate",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary=(
                "Install the PS-140 cross-package import gate for DISTRIBUTION."
            ),
            description=(
                "Materialises "
                "`tests/integration/test_cross_package_imports.py` "
                "declaring every module this package imports from a peer "
                "standalone (`scitex_<X>`) or the umbrella (`scitex.<X>`), "
                "each asserted with a real `import_module` call. The list "
                "is computed by the SAME function the PS-140 auditor "
                "grades against, so a freshly generated gate is clean by "
                "construction. Also creates `tests/integration/__init__.py` "
                "if missing. Re-run with `--force` after adding or "
                "removing a cross-package import — PS-140 fails on drift "
                "in either direction, so a stale entry is a violation too."
            ),
            examples=(
                Example(
                    "{prog} ecosystem install-cross-package-gate scitex-hpc",
                    "Install the gate.",
                ),
                Example(
                    "{prog} ecosystem install-cross-package-gate scitex-hpc --force",
                    "Regenerate after the import set changed.",
                ),
                Example(
                    "{prog} ecosystem install-cross-package-gate scitex-hpc --dry-run",
                    "Preview without writing.",
                ),
            ),
        ),
    )
    @click.argument("distribution")
    @click.option(
        "--force", is_flag=True, help="Overwrite an existing gate file."
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print the target path and contents without writing.",
    )
    @click.option(
        "--path",
        default=None,
        help=(
            "Checkout to write into. Same semantics as `audit-all --path`. "
            "Without it the cwd's repository is used; the "
            "`~/proj/<name>` registry guess is the last resort and is "
            "announced when used."
        ),
    )
    @click.option(
        "--repair-tail",
        is_flag=True,
        help=(
            "Also rewrite a PS-140 full-path `importorskip` guard below the "
            "closing sentinel into the root-split form. Off by default: the "
            "hand-owned region is preserved byte-identically unless you ask "
            "for this. Declines, loudly, on any tail whose shape cannot be "
            "proven."
        ),
    )
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def ecosystem_install_cross_package_gate(
        distribution, force, dry_run, path, repair_tail, yes
    ):
        # `install` is a MUTATING verb, so §2 of the CLI conventions requires a
        # --yes/-y flag on it regardless of how safe this particular
        # implementation is. Generation here is non-destructive without
        # --force, so nothing is gated on it today — but the flag is part of
        # the published shape of a mutating verb, and `install-audit-gate`
        # carries it for the same reason.
        del yes
        from ...._ecosystem import ECOSYSTEM, get_local_path

        if distribution not in ECOSYSTEM:
            click.echo(f"error: '{distribution}' not in ECOSYSTEM", err=True)
            raise SystemExit(2)
        info = ECOSYSTEM[distribution]
        if info.get("archived"):
            click.echo(f"skip  {distribution}: archived", err=True)
            raise SystemExit(0)

        local, target_source = resolve_write_target(distribution, path)
        if local is None or not local.exists():
            click.echo(
                f"error: local path for '{distribution}' missing: {local}",
                err=True,
            )
            raise SystemExit(2)

        assert_target_is_distribution(local, distribution, target_source)

        src_root = local / "src"
        if not src_root.exists():
            click.echo(
                f"error: {distribution} has no src/ at {src_root} — "
                "PS-140 only applies to src-layout packages",
                err=True,
            )
            raise SystemExit(2)

        own = _own_import_name(local)
        imports = sorted(_collect_cross_package_imports(src_root, own))
        target = local / "tests" / "integration" / "test_cross_package_imports.py"

        # No cross-package imports means PS-140 does not require the gate
        # at all. Writing an empty one would parametrize over nothing and
        # report green over zero assertions — a gate that cannot fail.
        if not imports:
            click.echo(
                f"{distribution}: no cross-package imports found under "
                f"{src_root} — PS-140 does not require a gate here, "
                "nothing written."
            )
            if target.exists():
                click.echo(
                    f"note: {target} exists but the import set is now empty; "
                    "PS-140 flags stale entries, so delete it or remove the "
                    "stale names by hand.",
                    err=True,
                )
            return

        # Read BEFORE rendering, so the tail we are about to preserve comes
        # from the file we are about to replace. Three outcomes, kept
        # distinct because collapsing them is how a regenerator eats a file:
        # a sentinel means user content to carry over verbatim; no sentinel
        # means there is no delimited user region to carry (announced, not
        # assumed); unreadable means REFUSE, because an unreadable file is
        # not an absent one.
        existing: str | None = None
        if target.exists():
            try:
                existing = target.read_text()
            except OSError as exc:
                click.echo(
                    f"error: {target} exists but could not be read ({exc}). "
                    "Refusing to overwrite — an unreadable gate is not an "
                    "absent one, and hand-written cases below the second "
                    "sentinel would be destroyed unseen.",
                    err=True,
                )
                raise SystemExit(1)

        split = split_at_sentinel(existing)
        if existing is not None and not split.has_sentinel:
            click.echo(
                f"note: {target} carries no '{END_SENTINEL}' marker, so no "
                "hand-written region is delimited in it. Anything below the "
                "generated list is REPLACED by this run. The rewritten file "
                "gains the sentinel pair, so future regenerations preserve "
                "that region.",
                err=True,
            )

        # PS-140's defect lives in the PRESERVED half, so the only way to fix
        # an existing gate through this command is to opt into touching that
        # half. Off by default and never silent in either direction: a repair
        # that happens without being asked for is the thing the preservation
        # policy exists to prevent, and a decline that is not printed leaves
        # the caller believing the sweep covered a file it skipped.
        tail = split.tail if split.has_sentinel else None
        tail_repaired = False
        if repair_tail and tail is not None:
            from ._gate_tail_repair import repair_tail as _repair

            outcome = _repair(tail)
            tail = outcome.tail
            tail_repaired = outcome.changed
            verb = "repaired" if outcome.changed else "left the tail alone"
            click.echo(f"repair-tail: {verb} — {outcome.reason}", err=True)
        elif repair_tail:
            click.echo(
                "repair-tail: no delimited tail to repair (the file is absent "
                "or carries no closing sentinel), so the generated body is "
                "written fresh and is already correct.",
                err=True,
            )

        content = render_cross_package_gate(distribution, imports, tail=tail)
        init = target.parent / "__init__.py"

        # Show WHAT was computed, not just where it will go. The reported
        # run wrote 3 imports where the branch had 4 — wrong tree in, wrong
        # content out. A gate that under-declares its imports PASSES while
        # missing one, which is exactly the failure PS-140 exists to catch,
        # so a silently-wrong list is worse than no gate.
        click.echo(
            f"computed {len(imports)} cross-package import(s) from {src_root}:",
            err=True,
        )
        for name in imports:
            click.echo(f"  - {name}", err=True)

        if dry_run:
            # SAY WHAT WOULD BE PRESERVED, not only what would be written.
            # Reported by scitex-hpc 2026-08-16 while agreeing to pilot the
            # 17-gate sweep: the way to prove the FIXED installer is the one
            # actually running is to dry-run it against a file with a known
            # hand-written tail and see it name those lines. Without this
            # line the dry-run of the new code is byte-indistinguishable from
            # the dry-run of the OLD destructive code — it simply never
            # mentions preserving anything, which reads identically to "this
            # file has no tail". A stale editable install would therefore
            # pass the very check meant to detect it.
            #
            # This is the §4 "merged is not live" trap with a specific
            # mechanism: the dist-info survives the source vanishing, so
            # version checks stay green while the import is broken (hpc
            # measured 20 days of exactly that in its own venv).
            if split.has_sentinel and tail_repaired:
                # NOT "verbatim". Saying preserved-verbatim while the guard
                # was rewritten would make the one line whose job is to prove
                # the preservation policy held into the line that hides a
                # change to it.
                click.echo(
                    f"# would REPAIR the {len(split.tail.splitlines())} line(s) "
                    f"below '{END_SENTINEL}' — the guard is rewritten, "
                    "everything else is preserved",
                    err=True,
                )
            elif split.has_sentinel:
                click.echo(
                    f"# would PRESERVE {len(split.tail.splitlines())} line(s) "
                    f"below '{END_SENTINEL}' verbatim",
                    err=True,
                )
            elif existing is not None:
                click.echo(
                    "# would REPLACE everything below the generated list "
                    "(no sentinel present to delimit a hand-written region)",
                    err=True,
                )
            click.echo(f"# would write: {target}")
            click.echo(content)
            if not init.exists():
                click.echo(f"# would write: {init}")
            return

        if target.exists() and not force:
            click.echo(
                f"error: {target} already exists (pass --force to overwrite)",
                err=True,
            )
            raise SystemExit(1)

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        if split.has_sentinel and tail_repaired:
            preserved = (
                f", REPAIRED the guard in the {len(split.tail.splitlines())} "
                "line(s) below the closing sentinel"
            )
        elif split.has_sentinel:
            preserved = (
                f", preserved {len(split.tail.splitlines())} line(s) below the "
                "closing sentinel"
            )
        else:
            preserved = ""
        click.echo(
            f"wrote {target} ({len(imports)} cross-package import(s)"
            f"{preserved})"
        )

        if not init.exists():
            init.write_text(
                '"""Integration tests — cross-package runtime gates."""\n'
            )
            click.echo(f"wrote {init}")

# EOF
