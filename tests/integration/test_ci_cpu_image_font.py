"""Contract for the minimal redistributable Japanese font in ci-cpu."""

from pathlib import Path

RECIPE = (
    Path(__file__).parents[2]
    / "src"
    / "scitex_dev"
    / "ci"
    / "runner"
    / "containers"
    / "ci-cpu.def"
)


def test_ci_cpu_pins_one_noto_cjk_jp_font_and_its_ofl_license() -> None:
    # Arrange
    text = RECIPE.read_text(encoding="utf-8")

    # Act
    required = (
        "523d033d6cb47f4a80c58a35753646f5c3608a78",
        "NotoSansCJKjp-Regular.otf",
        "68a3fc98800b2a27b371f2fb79991daf3633bd89309d4ffaa6946fd587f375b5",
        "6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2",
        "/usr/share/licenses/noto-cjk-jp/OFL-1.1.txt",
        "fc-cache -f",
    )

    # Assert
    assert all(value in text for value in required)