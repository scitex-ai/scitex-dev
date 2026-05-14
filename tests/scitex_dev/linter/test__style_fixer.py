"""Tests for `scitex_dev.linter._style_fixer`.

Covers the AST-based deletions for STX-P006/P007/P008/P009 + FM002/P004,
with explicit cases for the regex traps that motivated this fixer:
``linewidth=0.8`` (numeric eaten), kwargs as first/middle/last,
``s=`` only fired in scatter, plain Name calls vs Attribute calls,
syntax-error rollback, and notebooks via ``fixer.fix_file``.
"""

from __future__ import annotations

import json


from scitex_dev.linter._style_fixer import fix_style
from scitex_dev.linter.fixer import fix_file, fix_source


class TestFixStyleKwargs:
    def test_drops_fontsize_kwarg_from_set_xlabel(self):
        # Arrange
        # Act
        # Assert
        out = fix_style('ax.set_xlabel("x", fontsize=12)\n')
        assert out == 'ax.set_xlabel("x")\n'

    def test_drops_figsize_kwarg_from_subplots(self):
        # Arrange
        # Act
        # Assert
        out = fix_style("fig, ax = plt.subplots(figsize=(6, 3))\n")
        assert out == "fig, ax = plt.subplots()\n"

    def test_drops_linewidth_with_decimal(self):
        # The regex-trap case: linewidth=0.8 must not partially eat "0.8".
        # Arrange
        # Act
        # Assert
        out = fix_style("ax.plot([0, 1], [0, 1], '--', linewidth=0.8)\n")
        assert out == "ax.plot([0, 1], [0, 1], '--')\n"

    def test_drops_lw_short_form(self):
        # Arrange
        # Act
        # Assert
        out = fix_style("ax.axhline(0, lw=1.5)\n")
        assert out == "ax.axhline(0)\n"

    def test_drops_s_in_scatter(self):
        # Arrange
        # Act
        # Assert
        out = fix_style("ax.scatter([1, 2], [1, 2], s=10)\n")
        assert out == "ax.scatter([1, 2], [1, 2])\n"

    def test_drops_s_in_stx_scatter(self):
        # Arrange
        # Act
        # Assert
        out = fix_style("ax.stx_scatter([1, 2], [1, 2], s=10)\n")
        assert out == "ax.stx_scatter([1, 2], [1, 2])\n"

    def test_keeps_s_outside_scatter(self):
        # `s=` is a legitimate kwarg to ax.text() — must NOT be dropped.
        # Arrange
        # Act
        # Assert
        src = "ax.text(s='hello', x=0, y=0)\n"
        assert fix_style(src) == src

    def test_drops_first_kwarg_fontsize_not_in_out(self):
        # Kwarg immediately after `(` should swallow the trailing comma.
        # Arrange
        # Act
        # Assert
        out = fix_style("ax.plot(x, fontsize=10, label='a')\n")
        assert "fontsize" not in out
        # Result must still parse.
        import ast as _ast

        _ast.parse(out)


    def test_drops_first_kwarg_label_a_in_out(self):
        # Kwarg immediately after `(` should swallow the trailing comma.
        # Arrange
        # Act
        # Assert
        out = fix_style("ax.plot(x, fontsize=10, label='a')\n")
        assert "label='a'" in out
        # Result must still parse.
        import ast as _ast

        _ast.parse(out)

    def test_drops_last_kwarg(self):
        # Arrange
        # Act
        # Assert
        out = fix_style("ax.plot(x, label='a', fontsize=10)\n")
        assert out == "ax.plot(x, label='a')\n"

    def test_drops_middle_kwarg_fontsize_not_in_out(self):
        # Arrange
        # Act
        # Assert
        out = fix_style("ax.plot(x, label='a', fontsize=10, color='red')\n")
        assert "fontsize" not in out


    def test_drops_middle_kwarg_label_a_in_out(self):
        # Arrange
        # Act
        # Assert
        out = fix_style("ax.plot(x, label='a', fontsize=10, color='red')\n")
        assert "label='a'" in out


    def test_drops_middle_kwarg_color_red_in_out(self):
        # Arrange
        # Act
        # Assert
        out = fix_style("ax.plot(x, label='a', fontsize=10, color='red')\n")
        assert "color='red'" in out


class TestFixStyleLineCalls:
    def test_drops_tight_layout(self):
        # Arrange
        # Act
        # Assert
        out = fix_style("plt.tight_layout()\n")
        assert out == ""

    def test_drops_plt_show(self):
        # Arrange
        # Act
        # Assert
        out = fix_style("plt.show()\n")
        assert out == ""

    def test_drops_indented_tight_layout_tight_layout_not_in_out(self):
        # Arrange
        # Act
        # Assert
        out = fix_style("if True:\n    plt.tight_layout()\n    pass\n")
        # Whole indented line is dropped; surrounding scope stays.
        assert "tight_layout" not in out


    def test_drops_indented_tight_layout_pass_in_out(self):
        # Arrange
        # Act
        # Assert
        out = fix_style("if True:\n    plt.tight_layout()\n    pass\n")
        # Whole indented line is dropped; surrounding scope stays.
        assert "pass" in out


class TestFixStyleSafety:
    def test_preserves_already_clean(self):
        # Arrange
        # Act
        # Assert
        src = "ax.plot([1, 2], [1, 2])\n"
        assert fix_style(src) == src

    def test_rolls_back_on_syntax_error_in_input(self):
        # Arrange
        # Act
        # Assert
        bad = "ax.scatter([1, 2,\n"  # unclosed
        assert fix_style(bad) == bad

    def test_no_substitution_means_no_value_eaten(self):
        # The original regex bug ate "0.8" in linewidth=0.8 producing '--'.8.
        # AST-based deletion must produce balanced source.
        # Arrange
        # Act
        # Assert
        out = fix_style(
            "ax.plot([0, 1], [0, 1], '--', linewidth=0.8, label='perfect')\n"
        )
        # Crucially, no ".8" remains and the result parses.
        assert ".8" not in out
        import ast as _ast

        _ast.parse(out)


class TestFixFileNotebook:
    def test_fixes_notebook_in_place_changed_is_true(self, tmp_path):
        # Arrange
        # Act
        # Assert
        nb = {
            "cells": [
                {
                    "cell_type": "code",
                    "source": "ax.scatter([1, 2], [1, 2], s=10)\nplt.tight_layout()\n",
                    "metadata": {},
                    "outputs": [],
                    "execution_count": None,
                },
                {
                    "cell_type": "markdown",
                    "source": "# Heading\n",
                    "metadata": {},
                },
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        path = tmp_path / "x.ipynb"
        path.write_text(json.dumps(nb))

        result, changed = fix_file(str(path), write=True)
        assert changed is True
        loaded = json.loads(path.read_text())
        code_src = "".join(loaded["cells"][0]["source"])


    def test_fixes_notebook_in_place_s_10_not_in_code_src(self, tmp_path):
        # Arrange
        # Act
        # Assert
        nb = {
            "cells": [
                {
                    "cell_type": "code",
                    "source": "ax.scatter([1, 2], [1, 2], s=10)\nplt.tight_layout()\n",
                    "metadata": {},
                    "outputs": [],
                    "execution_count": None,
                },
                {
                    "cell_type": "markdown",
                    "source": "# Heading\n",
                    "metadata": {},
                },
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        path = tmp_path / "x.ipynb"
        path.write_text(json.dumps(nb))

        result, changed = fix_file(str(path), write=True)
        loaded = json.loads(path.read_text())
        code_src = "".join(loaded["cells"][0]["source"])
        assert "s=10" not in code_src


    def test_fixes_notebook_in_place_tight_layout_not_in_code_src(self, tmp_path):
        # Arrange
        # Act
        # Assert
        nb = {
            "cells": [
                {
                    "cell_type": "code",
                    "source": "ax.scatter([1, 2], [1, 2], s=10)\nplt.tight_layout()\n",
                    "metadata": {},
                    "outputs": [],
                    "execution_count": None,
                },
                {
                    "cell_type": "markdown",
                    "source": "# Heading\n",
                    "metadata": {},
                },
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        path = tmp_path / "x.ipynb"
        path.write_text(json.dumps(nb))

        result, changed = fix_file(str(path), write=True)
        loaded = json.loads(path.read_text())
        code_src = "".join(loaded["cells"][0]["source"])
        assert "tight_layout" not in code_src

    def test_skips_clean_notebook_changed_is_false(self, tmp_path):
        # Arrange
        # Act
        # Assert
        nb = {
            "cells": [
                {
                    "cell_type": "code",
                    "source": "ax.plot([1, 2], [1, 2])\n",
                    "metadata": {},
                    "outputs": [],
                    "execution_count": None,
                },
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        path = tmp_path / "clean.ipynb"
        path.write_text(json.dumps(nb))
        before_mtime = path.stat().st_mtime

        _, changed = fix_file(str(path), write=True)
        assert changed is False
        # File was not rewritten.


    def test_skips_clean_notebook_path_stat_st_mtime_before_mtime(self, tmp_path):
        # Arrange
        # Act
        # Assert
        nb = {
            "cells": [
                {
                    "cell_type": "code",
                    "source": "ax.plot([1, 2], [1, 2])\n",
                    "metadata": {},
                    "outputs": [],
                    "execution_count": None,
                },
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        path = tmp_path / "clean.ipynb"
        path.write_text(json.dumps(nb))
        before_mtime = path.stat().st_mtime

        _, changed = fix_file(str(path), write=True)
        # File was not rewritten.
        assert path.stat().st_mtime == before_mtime


class TestFixSourceIntegration:
    def test_fix_source_runs_style_fixer(self):
        # Arrange
        # Act
        # Assert
        src = "ax.scatter([1, 2], [1, 2], s=10)\n"
        out = fix_source(src)
        assert "s=10" not in out


# EOF
