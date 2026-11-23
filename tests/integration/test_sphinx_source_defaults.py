"""Published signatures must retain source defaults instead of build-host paths."""

import re
from html.parser import HTMLParser
from pathlib import Path


class _Signature(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag == "dt" and dict(attrs).get("id") == "scitex_dev._creds.rotate_all":
            self.active = True

    def handle_endtag(self, tag):
        if tag == "dt":
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.text.append(data)


def test_bundled_rotation_signature_preserves_its_source_default():
    # Arrange
    bundle = Path(__file__).resolve().parents[2] / "src/scitex_dev/_sphinx_html"
    parser = _Signature()
    # Act
    parser.feed((bundle / "api.html").read_text(encoding="utf-8"))
    signature = " ".join("".join(parser.text).split())
    # Assert: the source expression stays meaningful on every builder's HOME.
    assert re.search(r"source_path:\s*Path\s*=\s*CREDENTIALS_PATH", signature)
