---
description: |
  [TOPIC] Package ownership and dependency direction
  [DETAILS] Place work in the umbrella facade, Dev dispatcher, domain leaf,
  shared SDK or Hub host. Keep domain implementations in owning providers,
  distinguish standalone use from dependency-free use, and verify the five
  interfaces and declared dependency graph using source and installed metadata.
tags: [scitex-general-ecosystem-upstream-and-downstream]
---

# Package Ownership and Dependency Direction

Choose the owner of a capability before choosing an import or public command.
The ecosystem combines a public facade, domain libraries, shared contracts,
development tooling and a host. A strict three-layer diagram cannot describe
all of their declared dependencies.

## Ownership

| Package or role | Owns |
|---|---|
| `scitex` (`scitex-python` repository) | Unified discovery and public Python/CLI entry points; delegation and composition of leaf capabilities. |
| `scitex-dev` | Shared development, testing, documentation and release tooling; discovery and dispatch of package-owned auditors, hooks and skills. |
| Domain leaves | Domain algorithms, data semantics, implementations, interface providers and their domain-specific checks. |
| `scitex-sdk` | Shared GUI components, application/plugin contracts, Web API descriptors, route admission, schemas and host adapters; SDK-owned checks exposed to Dev. |
| `scitex-hub` | Authentication, users, projects, workspaces, plugin composition and deployment through SDK contracts and thin host adapters. |

SciTeX Cloud is the managed Hub deployment, not a separate library dependency
layer. The former `scitex-app` and `scitex-ui` components now belong to SDK;
retained component/provider labels do not identify independent distributions.
For example, SDK's `pyproject.toml` registers documentation and skills for
`scitex_sdk.app` and `scitex_sdk.ui` under those component names.

Agent Container, Cards, storage and scheduler tooling own their respective
infrastructure capabilities. Their responsibilities are independent of the orchestration implementation.
Dev also serves users outside the development team.
Users and external agents also consume its public interfaces.

## Dependency direction

The facade delegates specialized work to its owner. A domain leaf must remain
usable without installing the umbrella merely to reach its own implementation.
This does **not** mean it has no SciTeX dependencies: a leaf can require shared
SDK contracts, Dev tooling or another domain provider with a declared purpose.

Inspect the actual `pyproject.toml` dependencies, optional profiles, entry
points and runtime imports. Distinguish the runtime graph from development,
example and integration-test dependencies. A lower-bound dependency declaration
alone does not prove that all newer versions work.

Avoid cycles and duplicate implementations. Keep domain behavior in its leaf;
put generic discovery and enforcement in Dev, reusable GUI/Web contracts in
SDK, and identity/project/deployment integration in Hub. A leaf must not depend
on the hosted service merely to perform its local domain operation.

The umbrella is the deterministic pin point for coordinated member versions.
Leaves generally use compatible minimum floors; follow the
[release and pin doctrine](../05_development/14_release-and-pin-doctrine.md)
and [dependency guidance](02_dependency-and-version-pinning.md). Qualify the
resolved profile rather than assuming declared compatibility is sufficient.

## Composition and discovery

Conceptual I/O composition:

```text
scitex.io -> scitex_io -> the selected registered format handler
```

Check the owning implementation before assuming a registration protocol.
`scitex_io._registry` exposes saver/loader registration and lazily resolves
built-in handler tuples. Do not invent a universal entry-point spec dictionary
or claim every handler is imported during package import.

Dev discovers leaf-provided skills, documentation and audit plugins through
its declared provider mechanisms. SDK supplies application and Web API
contracts; Hub mounts the admitted leaf routes with host identity and project
scope. A provider declaration is not proof that its dependencies resolve or
that a host has enabled it.

## Five interfaces

Almost every package should expose its applicable capabilities through:

- Python API
- CLI
- MCP tools
- Web API
- Skills

Keep names, argument schemas, results and errors predictable across these
interfaces. Delegate to the same owning domain implementation; interface
adapters may translate their representation. Record a specific, justified
exception when an interface is inapplicable.

Report implementation, installed discovery, host enablement and live
availability separately. An installed MCP tool list is not an invocation test;
a GUI registration or HTTP 200 is not endpoint authorization acceptance.

## Tests follow behavior ownership

Test each package's own behavior where it is implemented. Add integration
coverage where a facade, registry, SDK or host composes providers. The umbrella
can have unit tests for its own dispatch, discovery and error handling; avoid
copying tests of delegated algorithms just to repeat their coverage.

Use the leaf's declared test/install profile and the owning CI procedure.
Do not assume every leaf uses the same extra or dependency-group syntax.
Exercise standalone operation in the appropriate resolved environment, plus
the required integration, error and side-effect cases in owned fixtures.

Dev's umbrella-dependency checks and real temporary-repository controls live
in `tests/scitex_dev/_cli/audit/_project/test__check_umbrella_dep_and_integration.py`.
They do not establish acceptance of every leaf or all five interfaces.

## Review checklist

- Identify the owning implementation, shared contract and host responsibility.
- Check declared dependencies and imports; preserve standalone domain use.
- Verify providers against source, installed metadata and the intended profile.
- Exercise own behavior and composition without duplicating domain logic.
- Check applicable interfaces and document justified exceptions.
- Qualify artifacts and served behavior separately; preserve failed checks.

Use the [documentation-drift procedure](../05_development/22_documentation-drift.md)
when reviewing these claims. Static fences, links and build checks do not
validate architecture prose or establish live deployment readiness.
