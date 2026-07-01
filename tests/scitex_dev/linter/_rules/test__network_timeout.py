"""Tests for STX-NET001 — outbound network call without an explicit timeout.

A dead/slow peer turns a timeout-less call into a multi-second connect-hang
(sac listen-daemon incident 2026-07-01: "everything is slow" fleet-wide). The
rule fires on unbounded urllib/requests/httpx/socket calls in non-test source,
stays silent when ``timeout`` is present (keyword OR positional where the API
takes it positionally), never touches test code, and never flags an arbitrary
``.get(`` (dict.get).
"""

from scitex_dev.linter._rules import NET001
from scitex_dev.linter.checker import lint_source


def _net001_ids(src, filepath="prod.py"):
    return [
        i.rule.id
        for i in lint_source(src, filepath=filepath)
        if i.rule.id == "STX-NET001"
    ]


# --- flagged: unbounded calls ------------------------------------------------


def test_flags_unbounded_urlopen_attribute():
    # Arrange
    src = "import urllib.request\nurllib.request.urlopen('http://x')\n"
    # Act
    ids = _net001_ids(src)
    # Assert
    assert ids == ["STX-NET001"]


def test_flags_unbounded_bare_urlopen():
    # Arrange
    src = "from urllib.request import urlopen\nurlopen('http://x')\n"
    # Act
    ids = _net001_ids(src)
    # Assert
    assert ids == ["STX-NET001"]


def test_flags_unbounded_requests_get():
    # Arrange
    src = "import requests\nrequests.get('http://x')\n"
    # Act
    ids = _net001_ids(src)
    # Assert
    assert ids == ["STX-NET001"]


def test_flags_unbounded_requests_post():
    # Arrange
    src = "import requests\nrequests.post('http://x', json={})\n"
    # Act
    ids = _net001_ids(src)
    # Assert
    assert ids == ["STX-NET001"]


def test_flags_unbounded_httpx_get():
    # Arrange
    src = "import httpx\nhttpx.get('http://x')\n"
    # Act
    ids = _net001_ids(src)
    # Assert
    assert ids == ["STX-NET001"]


def test_flags_unbounded_session_request():
    # Arrange
    src = "session.request('GET', 'http://x')\n"
    # Act
    ids = _net001_ids(src)
    # Assert
    assert ids == ["STX-NET001"]


def test_flags_unbounded_socket_create_connection():
    # Arrange
    src = "import socket\nsocket.create_connection(('h', 80))\n"
    # Act
    ids = _net001_ids(src)
    # Assert
    assert ids == ["STX-NET001"]


# --- passing: explicit timeout present --------------------------------------


def test_passes_requests_post_with_timeout_kwarg():
    # Arrange
    src = "import requests\nrequests.post('http://x', timeout=1.5)\n"
    # Act
    ids = _net001_ids(src)
    # Assert
    assert ids == []


def test_passes_httpx_with_timeout_kwarg():
    # Arrange
    src = "import httpx\nhttpx.get('http://x', timeout=2)\n"
    # Act
    ids = _net001_ids(src)
    # Assert
    assert ids == []


def test_passes_urlopen_positional_timeout():
    # Arrange
    src = "from urllib.request import urlopen\nurlopen('http://x', None, 3)\n"
    # Act
    ids = _net001_ids(src)
    # Assert
    assert ids == []


def test_passes_socket_positional_timeout():
    # Arrange
    src = "import socket\nsocket.create_connection(('h', 80), 2)\n"
    # Act
    ids = _net001_ids(src)
    # Assert
    assert ids == []


# --- never flag: test files + dict.get + suppression ------------------------


def test_does_not_flag_in_test_file():
    # Arrange
    src = "import requests\nrequests.get('http://x')\n"
    # Act
    ids = _net001_ids(src, filepath="tests/test_foo.py")
    # Assert
    assert ids == []


def test_does_not_flag_arbitrary_dict_get():
    # Arrange
    src = "d = {}\nd.get('key')\n"
    # Act
    ids = _net001_ids(src)
    # Assert
    assert ids == []


def test_stx_allow_comment_suppresses():
    # Arrange
    src = "import requests\nrequests.get('http://x')  # stx-allow: STX-NET001\n"
    # Act
    ids = _net001_ids(src)
    # Assert
    assert ids == []


# --- rule metadata pinned ---------------------------------------------------


def test_rule_id_pinned():
    # Arrange
    rule = NET001
    # Act
    rule_id = rule.id
    # Assert
    assert rule_id == "STX-NET001"


def test_default_severity_is_warning_not_error():
    # Arrange
    rule = NET001
    # Act
    severity = rule.severity
    # Assert
    assert severity == "warning"


def test_category_is_network():
    # Arrange
    rule = NET001
    # Act
    category = rule.category
    # Assert
    assert category == "network"
