#!/usr/bin/env python3
"""§1 bridge findings must name the package that SHIPS the bridge file.

THE DEFECT THESE TESTS PIN
--------------------------
`_check_bridge_pattern` grades `scitex/_mcp_tools/<short>.py` — a file that
ships in the UMBRELLA distribution. It used to report the verdict against
whichever package was being audited, at error-tier `§1`, inside that
package's REQUIRED merge gate. In scitex-io's CI that read:

    [§1] scitex-io: umbrella bridge `scitex/_mcp_tools/io.py` uses direct
         `mcp.mount(...)`

scitex-io cannot fix that file: it is not in its repository, it does not
declare the umbrella as a dependency (the umbrella arrives transitively),
and it cannot pin it.

THE CONTROL, measured before this change: scitex-io PR #167 resolved no
`scitex==` in its dependency set and showed NO §1 at all in its CI
headline, from the same repository and the same rule. The finding appeared
or vanished purely on whether the umbrella happened to be installed in
that job — which makes it a fact about the environment, not about the
package being graded.

WHY BOTH DIRECTIONS ARE HERE
----------------------------
A guard that has only seen the compliant case is untested, and the obvious
"fix" — stop reading the bridge at all — is an ecosystem-wide silent
disable that looks green. So these tests hold both poles:

  * a bad bridge whose OWNER is under audit is still an error-tier `§1`
    finding attributed to the owner;
  * the same bad bridge seen from a bystander's audit is still REPORTED
    (never dropped, still carrying the remedy) but as `§1u`, attributed to
    `scitex`, at warn tier — so it cannot fail the bystander's gate.

The bridge source comes through the module's own `read_bridge_source` /
`resolve_mcp_server` injection seams — the documented value seams, not
monkey-patching — because the umbrella is not installed in every
environment these tests run in. Nothing about the rule under test is
replaced.
"""

from __future__ import annotations

from scitex_dev._cli.audit._summary._audit import Violation
from scitex_dev._cli.audit._summary._mcp_bridge import (
    BRIDGE_OWNER,
    _check_bridge_pattern,
)
from scitex_dev._cli.audit._summary._severity import (
    RULE_SEVERITY,
    max_severity,
    severity_of,
)

#: A bridge that mounts the standalone the FastMCP-2.x-only way. Reduced
#: from `scitex/_mcp_tools/io.py` at scitex 2.28.13 — the version CI
#: resolved when this finding reached scitex-io's required check.
BAD_MOUNT_BRIDGE = (
    "def register_io_tools(mcp):\n"
    "    from scitex_io._mcp.server import mcp as io_mcp\n"
    "    mcp.mount(io_mcp)\n"
)

#: The other §1 shape: per-tool `@mcp.tool()` wrapping instead of a mount.
HAND_WRAP_BRIDGE = "@mcp.tool()\nasync def io_save(path: str) -> str:\n    pass\n"


def _findings(package: str, src: str) -> list[Violation]:
    """Run the real rule over `src` as if auditing `package`."""
    out: list[Violation] = []
    _check_bridge_pattern(
        package,
        out,
        read_bridge_source=lambda pkg: src,
        # Force a resolvable standalone so the hand-wrap branch's "no
        # alternative existed" exemption cannot silently absorb the case.
        resolve_mcp_server=lambda pkg: object(),
    )
    return out


class TestTheOwnerIsStillFlagged:
    """Direction 1 — the guard still bites the package that ships the file.

    SCOPE, STATED HONESTLY: these prove the owner branch GRADES correctly
    when it is entered. They do not claim it is entered in production
    today — `_mcp_audit._MCP_AUDIT_SKIP_PACKAGES` skips `scitex` before
    any rule runs, and `_short_name("scitex")` would send the rule after
    `scitex/_mcp_tools/scitex.py`, which is not where the umbrella's
    per-sub-package bridges live. Closing that needs the umbrella's audit
    to sweep its own bridge directory — a separate change, named in
    `_mcp_bridge`'s docstring so it is not mistaken for done.
    """

    def test_a_bad_bridge_in_the_owners_own_audit_is_reported(self):
        # Arrange
        package = BRIDGE_OWNER
        # Act
        out = _findings(package, BAD_MOUNT_BRIDGE)
        # Assert
        assert len(out) == 1

    def test_the_owners_finding_keeps_the_gating_rule_id(self):
        # Arrange
        package = BRIDGE_OWNER
        # Act
        out = _findings(package, BAD_MOUNT_BRIDGE)
        # Assert
        assert out[0].rule == "§1"

    def test_the_owners_finding_names_the_owner_as_its_subject(self):
        # Arrange
        package = BRIDGE_OWNER
        # Act
        out = _findings(package, BAD_MOUNT_BRIDGE)
        # Assert
        assert out[0].command == BRIDGE_OWNER

    def test_the_owners_finding_is_error_tier(self):
        """Error tier is what fails a gate — the owner CAN fix this file."""
        # Arrange
        package = BRIDGE_OWNER
        # Act
        out = _findings(package, BAD_MOUNT_BRIDGE)
        # Assert
        assert severity_of(out[0]) == "error"

    def test_the_owners_hand_wrap_finding_is_error_tier_too(self):
        """Both §1 shapes, not just the one the io incident happened to hit."""
        # Arrange
        package = BRIDGE_OWNER
        # Act
        out = _findings(package, HAND_WRAP_BRIDGE)
        # Assert
        assert severity_of(out[0]) == "error"


class TestABystanderIsNotGatedOnIt:
    """Direction 2 — a package that merely imported a bad umbrella."""

    def test_the_finding_is_still_reported(self):
        """Not dropped. Silencing it would be the green-by-absence 'fix'."""
        # Arrange
        package = "scitex-io"
        # Act
        out = _findings(package, BAD_MOUNT_BRIDGE)
        # Assert
        assert len(out) == 1

    def test_the_finding_is_attributed_to_the_umbrella(self):
        """`command` is what the printed line names — it must say `scitex`."""
        # Arrange
        package = "scitex-io"
        # Act
        out = _findings(package, BAD_MOUNT_BRIDGE)
        # Assert
        assert out[0].command == BRIDGE_OWNER

    def test_the_finding_carries_the_warn_tier_sibling_rule(self):
        # Arrange
        package = "scitex-io"
        # Act
        out = _findings(package, BAD_MOUNT_BRIDGE)
        # Assert
        assert out[0].rule == "§1u"

    def test_the_finding_is_warn_tier(self):
        # Arrange
        package = "scitex-io"
        # Act
        out = _findings(package, BAD_MOUNT_BRIDGE)
        # Assert
        assert severity_of(out[0]) == "warn"

    def test_the_bystanders_gate_stays_green(self):
        """`run_audit_mcp` returns `1 if max_severity(...) == "error" else 0`.

        This is that decision, taken over the real finding the real rule
        produced — the exit code audit-all aggregates and the required
        check reads.
        """
        # Arrange
        package = "scitex-io"
        # Act
        out = _findings(package, BAD_MOUNT_BRIDGE)
        # Assert
        assert max_severity(out) != "error"

    def test_the_hand_wrap_shape_is_downgraded_for_a_bystander_too(self):
        # Arrange
        package = "scitex-audio"
        # Act
        out = _findings(package, HAND_WRAP_BRIDGE)
        # Assert
        assert severity_of(out[0]) == "warn"

    def test_the_message_still_carries_the_remedy(self):
        """A downgrade that loses the fix instruction is a worse report."""
        # Arrange
        package = "scitex-io"
        # Act
        out = _findings(package, BAD_MOUNT_BRIDGE)
        # Assert
        assert "safe_mount" in out[0].message

    def test_the_message_says_which_repository_to_fix_it_in(self):
        """The reader of scitex-io's CI must not go looking in scitex-io."""
        # Arrange
        package = "scitex-io"
        # Act
        out = _findings(package, BAD_MOUNT_BRIDGE)
        # Assert
        assert f"Fix it in the `{BRIDGE_OWNER}` repository" in out[0].message

    def test_the_message_names_the_bystander_as_unable_to_fix_it(self):
        # Arrange
        package = "scitex-io"
        # Act
        out = _findings(package, BAD_MOUNT_BRIDGE)
        # Assert
        assert "`scitex-io` cannot" in out[0].message


class TestTheSiblingRuleIsRegistered:
    """An unregistered rule id defaults to `warn` silently — declare it."""

    def test_the_sibling_rule_has_a_declared_severity(self):
        # Arrange
        table = RULE_SEVERITY
        # Act
        declared = "§1u" in table
        # Assert
        assert declared is True

    def test_the_sibling_rule_is_declared_warn(self):
        # Arrange
        table = RULE_SEVERITY
        # Act
        severity = table["§1u"]
        # Assert
        assert severity == "warn"

    def test_the_owning_rule_is_still_declared_error(self):
        """The downgrade must not have leaked onto §1 itself."""
        # Arrange
        table = RULE_SEVERITY
        # Act
        severity = table["§1"]
        # Assert
        assert severity == "error"


class TestACleanBridgeStaysClean:
    """The rule must not have become a rule that always fires."""

    def test_a_safe_mount_bridge_produces_no_finding_for_the_owner(self):
        # Arrange
        src = (
            "from ._compat import safe_mount\n"
            "def register_io_tools(mcp):\n"
            "    safe_mount(mcp, sub_mcp, namespace='io')\n"
        )
        # Act
        out = _findings(BRIDGE_OWNER, src)
        # Assert
        assert out == []

    def test_a_safe_mount_bridge_produces_no_finding_for_a_bystander(self):
        # Arrange
        src = (
            "from ._compat import safe_mount\n"
            "def register_io_tools(mcp):\n"
            "    safe_mount(mcp, sub_mcp, namespace='io')\n"
        )
        # Act
        out = _findings("scitex-io", src)
        # Assert
        assert out == []


# EOF
