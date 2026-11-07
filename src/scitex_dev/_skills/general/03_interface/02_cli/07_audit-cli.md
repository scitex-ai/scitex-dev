---
description: |
  [TOPIC] Interface Cli Audit
  [DETAILS] SciTeX CLI automated audit — `scitex-dev ecosystem audit-cli`. Token classification, what it flags, custom dict format.
tags: [scitex-general-interface-cli-audit-cli]
---

# Audit CLI contracts

Use the auditor against the distribution and checkout being changed:

```bash
scitex dev ecosystem audit-cli scitex-dev --path "$PWD" --json
```

For an audit tied to a specific Python environment, run its module entry point:

```bash
python -m scitex_dev ecosystem audit-cli scitex-dev --path "$PWD" --json
python -m scitex_dev ecosystem audit-all scitex-dev --path "$PWD" --json
```

`audit-cli` inspects the Click command tree. `audit-all` also runs the other
interface and project auditors. CLI auditing and its dictionary data are part
of the base Dev installation; installing the compatibility `cli-audit` extra
is not an activation step.

## Read the actual verdict

Check both the process exit status and the JSON findings. Findings have rule
identifiers, command paths, messages and severities. Errors can fail the
configured gate; warnings are reported separately. A successful partial check
is not evidence that every interface or documented example works.

Use `--path` to bind the audit to the intended source tree. Record the imported
package origin and version when comparing a checkout with an installed
package. The current command's `--help` describes supported options; the
[coverage matrix](22_audit-cli-coverage-matrix.md) describes rule coverage.

Baseline and exclusion settings change the findings reported. Record masked
findings and coverage explicitly. Release acceptance requires the complete
configured gate; a quiet report produced by suppressing existing errors does
not establish conformance.

## Domain vocabulary

A standalone checkout can define domain terms in
`.scitex/dev/cli-audit-dict.yaml`. The auditor also supports a user-level
custom dictionary. These definitions extend the canonical catalog with
package-specific terms:

```yaml
nouns:
  - bibentry
  - openurl
transitive_verbs:
  - enrich
  - deduplicate
intransitive_verbs:
  - vacuum
verb_exceptions:
  - resolve  # why: DNS-style registry lookup, not completion of a task
```

Vocabulary describes intended meanings. It does not replace required flags,
working operations, concrete help examples or correct alias forwarding.
Use `CliHelp`, `SpecCommand` and `SpecGroup` for source-defined help rather
than maintaining another handwritten inventory.

## Installed and mounted command groups

An installed CLI can provide its dictionary as
`<top_level_import>/_cli_audit_dict.yaml`. Mounted-group auditing verifies the
loaded entry-point owner, exact distribution metadata and resource membership
and bytes in `RECORD`. Invalid or ambiguous ownership must remain visible;
the mounting application's dictionary must not supply a foreign group's
vocabulary when ownership fails.

A project-local file alone does not travel with a wheel. Keep one
authoritative source and make the package's real build backend emit the
resource. Dev's backend copies its canonical project dictionary into the
installable package, while its source distribution includes the original.
Verify both artifacts and an installed resource through the actual backend;
a source-file existence check does not prove installed behavior.

## Keeping this guidance current

Run the documented commands against the intended environment. Check source,
exit status, JSON findings and built artifacts separately. For recurring
review, use [periodic auditing](../../05_development/02_periodic-audits.md).
