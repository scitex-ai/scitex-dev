"""Parse installed headers once within one discovery, never across calls."""

from importlib import metadata


class _MetadataSnapshot:
    """Keep one consistent header view without caching installed state globally."""

    def __init__(self):
        self._headers = {}

    def headers(self, dist):
        key = id(dist)
        if key not in self._headers:
            # Retain the object so another distribution cannot reuse its id.
            self._headers[key] = (dist, dist.metadata)
        return self._headers[key][1]

    def version(self, dist):
        if type(dist) is metadata.PathDistribution:
            # The standard property reparses these same headers. Custom
            # distribution implementations retain their own version semantics.
            return self.headers(dist).get("Version")
        return dist.version
