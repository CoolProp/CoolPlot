# -*- coding: utf-8 -*-
"""The plotly backend: conformance, limitations and what plotly.js draws."""
import glob
from dataclasses import replace

import pytest

pytest.importorskip("plotly")

from coolplot.render.plotly import PlotlyRenderer, SYMBOL_WIDTH  # noqa: E402
from coolplot.render.testing import ALLOWED_LIMITATIONS, run_conformance  # noqa: E402
from coolplot.scene import AxesSpec, Markers, Scene  # noqa: E402
from coolplot.style.values import MarkerStyle  # noqa: E402


def test_plotly_passes_conformance():
    assert run_conformance(PlotlyRenderer) == []


def test_limitations_are_documented():
    assert PlotlyRenderer.limitations <= set(ALLOWED_LIMITATIONS)


class _NoHalo(PlotlyRenderer):
    def _annotate(self):
        super()._annotate()
        for annotation in self.figure.layout.annotations:
            annotation.font.shadow = None


class _DashesInPoints(PlotlyRenderer):
    def _apply(self, item):
        super()._apply(item)
        trace = self._traces[item.id]
        if trace.mode == "lines" and trace.line.dash not in (None, "solid"):
            trace.line.dash = ",".join("{0}px".format(float(v[:-2]) * 0.75) for v in trace.line.dash.split(","))


class _NoStacking(PlotlyRenderer):
    def _stack(self, item_id):
        self._traces[item_id].zorder = 0


class _LegendAlwaysUpperRight(PlotlyRenderer):
    def _set_legend(self, entries, style):
        super()._set_legend(entries, None if style is None else replace(style, location="upper right"))


class _MarkersNotCompensated(PlotlyRenderer):
    def _apply(self, item):
        super()._apply(item)
        trace = self._traces[item.id]
        if trace.mode == "markers":
            trace.marker.size = item.style.size_pt * 4.0 / 3.0


class _UnknownLimitation(PlotlyRenderer):
    limitations = frozenset({"line_caps", "text_order", "colours"})


@pytest.mark.parametrize("defect", [_NoHalo, _DashesInPoints, _NoStacking, _LegendAlwaysUpperRight,
                                    _MarkersNotCompensated, _UnknownLimitation])
def test_kit_rejects_plotly_defects(defect):
    assert run_conformance(defect) != []


def _chromium():
    pytest.importorskip("playwright")
    found = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    if not found:
        pytest.skip("no Chromium for Playwright")
    return found[-1]


@pytest.mark.parametrize("shape", sorted("os^vDx+"))
def test_plotly_draws_markers_as_wide_as_asked(shape):
    from playwright.sync_api import sync_playwright
    exe = _chromium()
    r = PlotlyRenderer(width=300, height=300)
    r.sync(Scene(AxesSpec(x_limits=(0.0, 1.0), y_limits=(0.0, 1.0)), [Markers(
        id="m", x=[0.5], y=[0.5], style=MarkerStyle(shape=shape, size_pt=30.0, face_color="#000000",
                                                   edge_color="#000000", edge_width_pt=0.0))]))
    html = r.figure.to_html(include_plotlyjs=True, full_html=True, div_id="cp")
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe)
        page = browser.new_page()
        page.set_content(html)
        page.wait_for_selector(".scatterlayer path.point")
        width = page.evaluate("document.querySelector('.scatterlayer path.point').getBBox().width")
        browser.close()
    assert width == pytest.approx(40.0, rel=0.01), SYMBOL_WIDTH
