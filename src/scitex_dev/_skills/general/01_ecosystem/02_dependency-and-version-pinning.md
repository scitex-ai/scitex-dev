---
description: |
  [TOPIC] Ecosystem dependency and version pinning
  [DETAILS] Declare required runtime providers, preserve standalone leaf use,
  avoid dependency cycles and qualify resolved profiles. Use compatible leaf
  floors and the umbrella's exact member pins under the release/pin doctrine.
  Distinguish current package profiles from the target extra/group policy.
tags: [scitex-general-ecosystem-dependency-and-version-pinning]
---

# Dependency Hygiene and Version Pinning

Use [package ownership](01_upstream-and-downstream.md) to choose the provider
of a capability. Inspect its source, declared dependencies and supported
installation profile before changing a dependency or recommending a command.
The [release and pin doctrine](../05_development/14_release-and-pin-doctrine.md)
controls coordinated release and umbrella pinning.

## Declare the actual runtime graph

A leaf's standalone operation must not require the umbrella to reach its own
domain implementation. It can depend on justified SciTeX peers such as SDK,
Dev, I/O or another domain library. Current FigRecipe declares SDK and Dev
runtime dependencies; standalone does not mean no SciTeX packages are installed.

For each import, determine whether it is required at runtime, optional for an
explicit capability, or needed only by development, documentation or integration
tests. Declare it in the appropriate owning profile and exercise that profile.
Avoid dependency cycles and keep the implementation with its domain owner.

| Relationship | Review requirement |
|---|---|
| Leaf to shared SDK or another leaf | Declare the required interface and compatible version floor; verify resolution and behavior. |
| Package to Dev | Distinguish runtime discovery/tooling from test-only utilities; declare the applicable dependency. |
| Leaf to umbrella | Keep local domain operations independent of the umbrella; review example/test dependencies separately. |
| Leaf application to Hub | Keep domain behavior reusable outside the service; use SDK contracts and thin host adapters for identity/project integration. |
| Umbrella to members | Delegate to owning providers and exact-pin the qualified coordinated cohort. |

A lower bound tells the installer which versions it may select. It does not
prove that every selected version combination works. An import-only smoke
check or a compatible dependency graph also does not establish behavior.

## Minimum floors and deterministic pins

A leaf generally declares a compatible minimum for each required SciTeX
provider. Raise that floor when its implementation starts using an interface
introduced by a newer provider version, and verify the documented minimum
where supported by the owning test procedure.

The umbrella is the deterministic pin point: it exact-pins coordinated SciTeX
members. Do not apply a blanket ban on exact pins to the umbrella, or copy its
entire exact-pinned cohort into every leaf. A standalone leaf can resolve a
newer compatible provider; an umbrella installation selects its qualified pins.

Use the release/pin doctrine for third-party bounds, deployment pins and
coordinated waves. Document a compatibility or security bound with its reason
and follow-up. Keep source version changes, published artifacts, installed
profiles and live service adoption as separate facts.

## Optional capabilities and test profiles

A required capability must declare its runtime dependency. An optional
capability must have a documented installation path and a clear refusal when
that dependency is absent. Avoid broad import fallbacks that hide a broken
required installation.

The target public extra/group policy is documented in
[26_the-only-extra-is-all.md](26_the-only-extra-is-all.md). Migration state is
not uniform across existing packages. Inspect the actual leaf's `pyproject.toml`,
CLI help and qualified CI helper before recommending an install command; a
requested dependency group and a published extra are different mechanisms.
Do not silently migrate profiles or weaken an audit to make an example pass.

Use the owning full test profile for release qualification. Record absent,
skipped, incomplete or failed coverage explicitly; do not replace a failed
full install with reduced dependencies and call it accepted. The
[development dependency guide](19_dev-extras-completeness.md) covers profile
completeness; source and installed evidence remain necessary.

## Coordinated changes

1. Implement and test the capability in its owning provider.
2. Qualify and publish through that provider's normal release procedure.
3. Update consumers that use the new interface, including their minimum floors.
4. Refresh the umbrella's exact pins only against published, qualified members.
5. Resolve and test the intended consumer cohort, then qualify the artifact and
   any host rollout separately.

A producer release alone does not require every consumer to raise its floor.
For a breaking change, qualify both the changed interface and affected consumer
code; do not treat a version edit as behavioral acceptance. Preserve immutable
published versions and failed qualification evidence.

## Review checklist

- Identify the owning runtime capability and justify every dependency.
- Keep leaf domain operation independent of the umbrella and hosted service.
- Check peer minima and the umbrella's exact coordinated pins.
- Inspect the actual optional, test and documentation profiles.
- Verify normal resolution, required behavior and error cases in owned fixtures.
- Record the source, installed versions, artifacts and tested interface scope.
- Follow ordinary release gates; retain incomplete and failed results.

See Dev's umbrella dependency controls in
`tests/scitex_dev/_cli/audit/_project/test__check_umbrella_dep_and_integration.py`.
These checks cover their declared rules, not every relationship in this guide.
