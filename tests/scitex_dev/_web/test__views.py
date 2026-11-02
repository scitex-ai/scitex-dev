"""Actual registry, SDK admission and isolated Django requests; no server."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _child(code):
    root = Path(__file__).resolve().parents[3] / "src"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys\nsys.path.insert(0, " + repr(str(root)) + ")\n" + code,
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_basic_dev_import_has_no_optional_web_runtime():
    """A fresh basic Dev import does not load SDK, Django or the Web adapter."""
    # Arrange
    # Act
    result = _child("""import json
import scitex_dev
json.dump([name for name in sys.modules if name.startswith(("scitex_sdk", "django", "scitex_dev._web"))], sys.stdout)
""")
    # Assert
    assert result == []


def test_actual_public_registry_projection_and_method_refusal():
    """Real GET returns actual names only; mutation methods are refused."""
    # Arrange
    # Act
    result = _child("""import json
from django.conf import settings
settings.configure(DEFAULT_CHARSET="utf-8")
from django.test import RequestFactory
from scitex_dev import get_all_packages
from scitex_dev._web._views import curated_packages
factory = RequestFactory()
response = curated_packages(factory.get("/ecosystem/packages", {"package": "/private/not-a-name"}))
post = curated_packages(factory.post("/ecosystem/packages"))
payload = json.loads(response.content)
json.dump({"payload": payload, "expected": sorted(set(get_all_packages())), "get": response.status_code, "post": post.status_code, "allow": post.headers["Allow"], "content_type": response.headers["Content-Type"]}, sys.stdout)
""")
    observed = {
        "payload": result["payload"],
        "names_are_public": bool(result["expected"])
        and all(isinstance(x, str) and "/" not in x for x in result["expected"]),
        "get": result["get"],
        "post": result["post"],
        "allow": result["allow"],
        "type": result["content_type"],
    }
    # Assert
    assert observed == {
        "payload": {"catalog": "curated", "packages": result["expected"]},
        "names_are_public": True,
        "get": 200,
        "post": 405,
        "allow": "GET",
        "type": "application/json",
    }


def test_descriptor_roundtrip_and_real_sdk_admission():
    """Unadmitted resolution fails; explicit admission resolves the real view."""
    # Arrange
    # Act
    result = _child("""import json
from scitex_sdk.app.api_plugin import ApiPluginRef
from scitex_sdk.app.api_mount import admit, resolve_handler, AdmissionDenied, dump_inert_descriptor
from scitex_dev._web._api import plugin
ref = ApiPluginRef(name="scitex-dev", target="scitex_dev._web._api:plugin", distribution="scitex-dev")
empty = admit(ref, review_ref="owned-fixture-denied", enabled=())
try:
    resolve_handler(ref, empty, "ecosystem/packages")
except AdmissionDenied:
    refused = True
else:
    refused = False
allowed = admit(ref, review_ref="owned-fixture-accepted", enabled=("ecosystem/packages",))
handler = resolve_handler(ref, allowed, "ecosystem/packages")
from scitex_dev._web._views import curated_packages
fragment = plugin.openapi_fragment()
serialized = json.loads(dump_inert_descriptor(plugin))
route = plugin.routes[0]
json.dump({"denied": refused, "handler": handler is curated_packages, "path": route.path, "readonly": route.read_only, "public": route.auth.public, "project": route.auth.project_scope, "serialized": serialized, "fragment": fragment}, sys.stdout)
""")
    observed = {
        "denied": result["denied"],
        "handler": result["handler"],
        "path": result["path"],
        "readonly": result["readonly"],
        "public": result["public"],
        "project": result["project"],
        "id": result["serialized"]["id"],
        "has_path": "ecosystem/packages" in str(result["fragment"]),
        "has_schema": "CuratedPackages" in str(result["fragment"]),
    }
    # Assert
    assert observed == {
        "denied": True,
        "handler": True,
        "path": "ecosystem/packages",
        "readonly": True,
        "public": True,
        "project": "none",
        "id": "scitex-dev",
        "has_path": True,
        "has_schema": True,
    }


def test_web_extras_are_optional_and_entrypoint_declares_real_object():
    """Packaging declares the optional adapter without adding a core cycle."""
    # Arrange
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    # Act
    metadata = tomllib.loads(
        (Path(__file__).resolve().parents[3] / "pyproject.toml").read_text()
    )
    project = metadata["project"]
    observed = {
        "binding": project["entry-points"]["scitex.apis"],
        "core_web": [
            x for x in project["dependencies"] if x.startswith(("scitex-sdk", "django"))
        ],
        "optional": {
            extra: (
                any(
                    x.startswith("scitex-sdk>=0.3.18")
                    for x in project["optional-dependencies"][extra]
                ),
                "django>=4.2" in project["optional-dependencies"][extra],
            )
            for extra in ("all", "dev")
        },
    }
    # Assert
    assert observed == {
        "binding": {"scitex-dev": "scitex_dev._web._api:plugin"},
        "core_web": [],
        "optional": {"all": (True, True), "dev": (True, True)},
    }


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "HEAD", "OPTIONS"])
def test_method_refusal_matches_sdk_declared_json_error(method):
    """Each rejected method has the declared machine-readable error and Allow header."""
    # Arrange
    script = """import json
from django.conf import settings
settings.configure(DEFAULT_CHARSET="utf-8")
from django.test import RequestFactory
from scitex_dev._web._views import curated_packages
from scitex_dev._web._api import plugin
response = curated_packages(RequestFactory().generic(METHOD, "/ecosystem/packages"))
error = next(item for item in plugin.routes[0].errors if item.status == response.status_code)
body = json.loads(response.content)
json.dump({"status": response.status_code, "allow": response.headers.get("Allow"), "content_type": response.headers.get("Content-Type"), "error": body.get("error"), "declared": {"code": error.code, "message": error.message}, "declared_status": error.status}, sys.stdout)
""".replace("METHOD", repr(method))
    # Act
    result = _child(script)
    observed = (
        result["status"],
        result["allow"],
        result["content_type"],
        result["error"],
        result["declared_status"],
        result["declared"]["code"],
    )
    # Assert
    assert observed == (
        405,
        "GET",
        "application/json",
        result["declared"],
        405,
        "method_not_allowed",
    )
