"""The installed documentation must retain the authored guides and search UI."""

from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs" / "sphinx"
BUNDLE = ROOT / "src" / "scitex_dev" / "_sphinx_html"
GUIDES = sorted(SOURCE.glob("*.rst"))
assert GUIDES, "No authored Sphinx guides found; refusing an empty scope"


class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.heading = []
        self.in_heading = False
        self.in_permalink = False
        self.heading_finished = False
        self.in_form = False
        self.query_form = False

    def handle_starttag(self, tag, attrs):
        if tag == "h1" and not self.heading_finished:
            self.in_heading = True
        if (
            tag == "a"
            and self.in_heading
            and "headerlink" in (dict(attrs).get("class") or "").split()
        ):
            self.in_permalink = True
        if tag == "form":
            self.in_form = True
        if tag == "input" and self.in_form and dict(attrs).get("name") == "q":
            self.query_form = True

    def handle_endtag(self, tag):
        if tag == "a":
            self.in_permalink = False
        if tag == "h1" and self.in_heading:
            self.in_heading = False
            self.heading_finished = True
        if tag == "form":
            self.in_form = False

    def handle_data(self, data):
        if self.in_heading and not self.in_permalink:
            self.heading.append(data)


def _source_title(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    for title, underline in zip(lines, lines[1:]):
        title, underline = title.strip(), underline.strip()
        if (
            title
            and len(underline) >= len(title)
            and len(set(underline)) == 1
            and underline[0] in '=-~^"`+*'
        ):
            return title
    raise AssertionError(f"No plain top-level guide title found in {path}")


@pytest.mark.parametrize("guide", GUIDES, ids=lambda path: path.stem)
def test_bundled_guide_keeps_its_authored_title(guide):
    # Arrange: the wheel ships this resource directory, not the CI build tree.
    page = BUNDLE / (guide.stem + ".html")
    parser = _Page()
    # Act
    # Missing resources raise here; there is no empty-page fallback.
    parser.feed(page.read_text(encoding="utf-8"))
    title = " ".join("".join(parser.heading).split())
    # Assert: catches stale bundles and Sphinx's authored search.rst collision.
    assert title == _source_title(guide)


def test_bundled_search_retains_the_generated_query_form():
    # Arrange
    parser = _Page()
    # Act
    parser.feed((BUNDLE / "search.html").read_text(encoding="utf-8"))
    # Assert
    assert parser.query_form, "Bundled search page lost its generated query form"
