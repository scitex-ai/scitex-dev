"""Diagnostic metadata locations; never select or suppress provider declarations."""


def _entry_point_origin(point) -> str:
    """Describe importlib's metadata record, if available on this entry point.

    PathDistribution keeps the actual dist-info/egg-info location in `_path`.
    Other metadata implementations and injected entry points may omit it;
    diagnostic availability must not affect duplicate-provider admission.
    """
    path = getattr(getattr(point, "dist", None), "_path", None)
    return f"metadata: {path if path is not None else '<unavailable>'}"
