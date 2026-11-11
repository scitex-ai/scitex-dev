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
of the base Dev installation. The retired `cli-audit` extra is not a supported
activation step.

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
`<top_level_import>/_cli_audit_dict.yaml`. Root and mounted-group auditing verify
the loaded entry-point owner, exact distribution metadata and resource membership
and bytes in `RECORD`. A RECORD-owned root uses this boundary too: a missing or
invalid dictionary cannot borrow words from the current project's dictionary.
Ambiguous installed owners remain reported. Source checkouts retain the separate
source-subject admission described below; an unrecorded source claim alone does
not gain installed authority. A mounting application's dictionary must not supply
a foreign group's vocabulary when ownership fails.

The current source also attributes nested callbacks published by an already
loaded ordinary Python module. It first verifies a loaded console source for
that namespace, then checks the callback's own module membership in the
distribution's `RECORD`. A Python-function console bootstrap can establish
that source without being invoked. Namespace spelling alone is insufficient.
Exact console claims retain priority, including rejected claims; a nested
binding cannot rescue them. Missing, tampered or ambiguous resources still
exclude the parent dictionary.

A lazy facade can establish ownership when its plain Python Click class is
defined and published in the loaded console module. Both that module and its published
callback's module must belong to the same exact distribution's `RECORD` and
pass containment checks, even across different top-level namespaces. Dev does
not call `__getattr__`, load entry points or invoke callbacks for this inference.
Custom metaclasses and unpublished class bindings remain unsupported.
A known console class with an unbound callback excludes parent vocabulary.

A qualified facade anchors its callback namespace; each nested callback still
needs its own source membership. Cache entries distinguish command classes
sharing a callback. Existing source claims retain priority, including rejections.
Source membership establishes attribution, not source-content or behavior
attestation; dictionary bytes require their recorded size/hash.

Each walk freezes the first resource verdict and verified bytes for a metadata
origin. Nested lookups cannot substitute later file contents or repair an
already rejected resource within that snapshot. Callback-module membership is
checked separately: an unrecorded child cannot use a verified parent dictionary
even when both claim the same distribution.

This added inference does not import modules or call business callbacks.
Unpublished dynamic callbacks and opaque callable objects remain outside its
scope. Older installed releases may lack this attribution; inspect the actual
owner provenance before assuming a dictionary will apply. Behavioral controls
are in `tests/scitex_dev/_cli/audit/_summary/test__callback_source.py` and the
`test__mounted_owner.py`. Class-binding controls
live in `test__facade_source.py`. Also exercise
the leaf's actual installed wheel: verify source attribution, exclusion of
parent vocabulary when its dictionary is missing, unrecorded source refusal
and ambiguous metadata refusal.

A project-local file alone does not travel with a wheel. Keep one
authoritative source and make the package's real build backend emit the
resource. Dev's backend copies its canonical project dictionary into the
installable package, while its source distribution includes the original.
Verify both artifacts and an installed resource through the actual backend;
a source-file existence check does not prove installed behavior.

## Explicitly audited source

For the audit's own source checkout, the current source can use its declared
dictionary when the project name and console entry point match the selected
owner, and the loaded console and callback modules belong to that checkout's
namespace. The project policy above takes precedence; otherwise a checked-in
`<top_level_import>/_cli_audit_dict.yaml` supplies the source policy. Paths must
remain within the audited tree. Missing declarations, wrong module origins and
ambiguous metadata cannot establish this source context.
The source resource must be a regular UTF-8 file of at most 1 MiB and remain
unchanged while its bytes are captured.

The walk freezes the selected source bytes and reports their path and SHA256
as an **audited source subject**, not an installed RECORD claim. Returning from
a mounted provider to a callback owned by that source restores its dictionary.
This does not grant a foreign callback the root's vocabulary or relax installed
resource checks. Controls using real Dev and SDK groups live in
`tests/scitex_dev/_cli/audit/_summary/test__source_dictionary.py`; its isolated
child runs the actual source cases with one installed metadata origin. An
editable target, source egg-info and baked wheel can expose distinct origins
for the same package. That remains an ambiguous verdict, not source authority.
An older installed Dev may lack this behavior. Source attribution alone does
not establish an installed artifact's contents or a command's business behavior.

## Keeping this guidance current

Run the documented commands against the intended environment. Check source,
exit status, JSON findings and built artifacts separately. For recurring
review, use [periodic auditing](../../05_development/02_periodic-audits.md).
