"""Thin optional Django adapter; no config changes, leaf imports or fleet probes."""


def curated_packages(request):
    """Return only names from the existing public curated-registry operation.

    The SDK descriptor requires explicit host admission; this module neither
    starts a server nor mounts a URL. No registry metadata/paths, installed
    versions, process status, configuration or documentation introspection
    cross the boundary.
    """
    try:
        from django.http import JsonResponse
    except ImportError as exc:
        raise ImportError(
            "The optional Dev Web adapter requires scitex-dev[all]."
        ) from exc

    if request.method != "GET":
        response = JsonResponse(
            {
                "error": {
                    "code": "method_not_allowed",
                    "message": "Use GET for the curated package catalog.",
                }
            },
            status=405,
        )
        response["Allow"] = "GET"
        return response
    from scitex_dev import get_all_packages

    return JsonResponse(
        {"catalog": "curated", "packages": sorted(set(get_all_packages()))}
    )
