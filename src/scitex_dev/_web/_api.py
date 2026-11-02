"""Inert SDK declaration for a real public curated-package catalog."""

try:
    from scitex_sdk.app.api_plugin import (
        ApiField,
        ApiPlugin,
        ApiRoute,
        ApiSchema,
        AuthScope,
        RateLimit,
    )
except ImportError as exc:
    raise ImportError(
        "The optional Dev Web API requires Python >=3.10 and scitex-dev[all]."
    ) from exc

plugin = ApiPlugin(
    id="scitex-dev",
    title="SciTeX Dev",
    api_version="1.0.0",
    routes=(
        ApiRoute(
            path="ecosystem/packages",
            methods=("GET",),
            response=ApiSchema(
                name="CuratedPackages",
                fields=(
                    ApiField(
                        name="catalog",
                        type="string",
                        enum=("curated",),
                        description="Scope of this data: curated ecosystem registry only.",
                    ),
                    ApiField(
                        name="packages",
                        type="array",
                        description="Sorted unique package-name strings; not installed, live, or complete fleet membership.",
                    ),
                ),
            ),
            rate=RateLimit(rate_class="interactive", compute_cost="low"),
            auth=AuthScope(public=True, project_scope="none"),
            handler="scitex_dev._web._views:curated_packages",
            read_only=True,
        ),
    ),
)
