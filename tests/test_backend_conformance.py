# -*- coding: utf-8 -*-
"""Every backend shipped with CoolPlot has to pass the conformance kit."""
import pytest

from CoolPlot.render.svg import SvgRenderer
from CoolPlot.render.testing import run_conformance


def _mpl_factory():
    pytest.importorskip("matplotlib")
    from CoolPlot.render.mpl import MatplotlibRenderer
    return lambda: MatplotlibRenderer(use_pyplot=False)


@pytest.mark.parametrize("name", ["svg", "matplotlib"])
def test_backend_passes_conformance(name):
    factory = SvgRenderer if name == "svg" else _mpl_factory()
    assert run_conformance(factory) == []


def test_kit_rejects_a_backend_that_ignores_styles():
    """The kit has to fail a backend that draws everything in default styles."""

    class Lazy(SvgRenderer):
        def _add(self, item):
            from dataclasses import replace
            super()._add(replace(item, style=type(item.style)()))

    failures = run_conformance(Lazy)
    assert any("[style]" in f for f in failures)
