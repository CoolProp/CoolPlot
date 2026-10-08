# -*- coding: utf-8 -*-
"""Every backend shipped with CoolPlot has to pass the conformance kit, and
the kit has to reject backends that break a requirement.

The second half plants one defect at a time in a working backend and
checks that the kit notices. Each defect is a requirement from
docs/backends.md that an earlier version of the kit let through.
"""
import math
import re
from dataclasses import replace

import pytest

from CoolPlot.render.svg import SvgRenderer
from CoolPlot.render.testing import run_conformance


def _mpl_factory(cls=None):
    pytest.importorskip("matplotlib")
    from CoolPlot.render.mpl import MatplotlibRenderer
    cls = cls or MatplotlibRenderer
    return lambda: cls(use_pyplot=False)


@pytest.mark.parametrize("name", ["svg", "matplotlib"])
def test_backend_passes_conformance(name):
    factory = SvgRenderer if name == "svg" else _mpl_factory()
    assert run_conformance(factory) == []


# ---------------------------------------------------------------------------
# Planted defects in the SVG backend
# ---------------------------------------------------------------------------
def _svg_postprocessed(edit):
    """An SvgRenderer whose output is changed by ``edit(text) -> text``."""
    class Mutant(SvgRenderer):
        def to_svg(self):
            return edit(super().to_svg())
    return Mutant


def _drop_all_but_first(cls_name):
    def edit(text):
        lines = text.split("\n")
        hits = [i for i, ln in enumerate(lines) if 'class="{0}"'.format(cls_name) in ln]
        return "\n".join(ln for i, ln in enumerate(lines) if i not in hits[1:])
    return edit


def _grid_above_items(text):
    lines = text.split("\n")
    grid = [ln for ln in lines if "cp-grid-" in ln]
    rest = [ln for ln in lines if "cp-grid-" not in ln]
    return "\n".join(rest[:-1] + grid + rest[-1:])


def _svg_style_override(method, **changes):
    """Draw one part of the axes decoration with a wrong style."""
    class Mutant(SvgRenderer):
        pass

    def patched(self, to_px, axes):
        return getattr(SvgRenderer, method)(self, to_px, replace(axes, style=replace(axes.style, **changes)))
    setattr(Mutant, method, patched)
    return Mutant


class _LegendAlwaysUpperRight(SvgRenderer):
    def _legend_elements(self):
        saved = self._legend_style
        if saved is not None:
            self._legend_style = replace(saved, location="upper right")
        try:
            return super()._legend_elements()
        finally:
            self._legend_style = saved


class _LegendWithoutSamples(SvgRenderer):
    def _legend_sample(self, item, x, cy):
        return []


class _TextAngleInDataSpace(SvgRenderer):
    def _text(self, item, to_px):
        text = super()._text(replace(item, direction=None), to_px)
        if item.direction is None or not text:
            return text
        angle = -math.degrees(math.atan2(item.direction[1], item.direction[0]))
        return text.replace("rotate(0 ", "rotate({0:.3f} ".format(angle))


def _upside_down(text):
    return re.sub(r'(data-item="text/left-[a-z]+".*?rotate\()(-?[0-9.]+)',
                  lambda m: m.group(1) + str(float(m.group(2)) + 180.0), text)


class _HiddenItemsInAutoscale(SvgRenderer):
    def _limits(self):
        saved = self._items
        self._items = {k: replace(v, visible=True) for k, v in saved.items()}
        try:
            return super()._limits()
        finally:
            self._items = saved


SVG_DEFECTS = {
    "casing ignores dash": _svg_postprocessed(
        lambda t: re.sub(r'(class="cp-casing"[^>]*?) stroke-dasharray="[^"]*"', r"\1", t)),
    "casing ignores alpha": _svg_postprocessed(
        lambda t: re.sub(r'(class="cp-casing"[^>]*?stroke-opacity=")[^"]*"', r'\g<1>1"', t)),
    "one grid line only": _svg_postprocessed(_drop_all_but_first("cp-grid-major")),
    "grid width ignored": _svg_postprocessed(
        lambda t: re.sub(r'(class="cp-grid-major"[^>]*?stroke-width=")[^"]*"', r'\g<1>1"', t)),
    "minor grid dropped": _svg_postprocessed(lambda t: re.sub(r'<line class="cp-grid-minor"[^>]*/>\n?', "", t)),
    "grid above items": _svg_postprocessed(_grid_above_items),
    "axis label font ignored": _svg_postprocessed(
        lambda t: re.sub(r'(class="cp-[xy]-label"[^>]*?font-size=")[^"]*"', r'\g<1>13.333"', t)),
    "title font ignored": _svg_postprocessed(
        lambda t: re.sub(r'(class="cp-title"[^>]*?font-weight=")bold"', r'\1normal"', t)),
    "tick label font ignored": _svg_postprocessed(
        lambda t: re.sub(r'(class="cp-tick-label"[^>]*?font-size=")[^"]*"', r'\g<1>14"', t)),
    "figure background ignored": _svg_postprocessed(
        lambda t: re.sub(r'(class="cp-figure"[^>]*?fill=")[^"]*"', r'\1white"', t)),
    "tick length ignored": _svg_style_override("_ticks_and_labels", tick_length_pt=3.5),
    "tick width ignored": _svg_style_override("_ticks_and_labels", tick_width_pt=0.8),
    "legend location ignored": _LegendAlwaysUpperRight,
    "legend samples missing": _LegendWithoutSamples,
    "text angle in data space": _TextAngleInDataSpace,
    "text upside down": _svg_postprocessed(_upside_down),
    "hidden items in autoscale": _HiddenItemsInAutoscale,
    "markers drawn too small": _svg_postprocessed(lambda t: re.sub(r'(<circle [^>]*?r=")[^"]*"', r'\g<1>0.667"', t)),
}


@pytest.mark.parametrize("defect", sorted(SVG_DEFECTS))
def test_kit_rejects_svg_defect(defect):
    assert run_conformance(SVG_DEFECTS[defect]) != []


def test_kit_rejects_a_backend_that_ignores_styles():
    class Lazy(SvgRenderer):
        def _add(self, item):
            super()._add(replace(item, style=type(item.style)()))

    assert any("[style]" in f for f in run_conformance(Lazy))


# ---------------------------------------------------------------------------
# Planted defects in the matplotlib backend
# ---------------------------------------------------------------------------
def _mpl_defects():
    pytest.importorskip("matplotlib")
    from matplotlib import patheffects
    from CoolPlot.render.mpl import MatplotlibRenderer
    from CoolPlot.scene import Line, Markers, Text

    class CasingWithoutLine(MatplotlibRenderer):
        def _apply(self, artist, item):
            super()._apply(artist, item)
            if isinstance(item, Line) and artist.get_path_effects():
                artist.set_path_effects([e for e in artist.get_path_effects()
                                         if isinstance(e, patheffects.Stroke)])

    class AutoscaleWithHidden(MatplotlibRenderer):
        def _finish(self, report):
            if report.changed and self._axes is not None and self._axes.x_limits is None:
                self.ax.relim(visible_only=False)
                self.ax.autoscale_view()

    class NotUpright(MatplotlibRenderer):
        def _apply(self, artist, item):
            super()._apply(artist, item)
            if isinstance(item, Text) and item.direction is not None:
                artist.set_rotation(math.degrees(math.atan2(item.direction[1], item.direction[0])))

    class ClipsLogValues(MatplotlibRenderer):
        def _set_axes(self, axes):
            super()._set_axes(axes)
            if axes.y_log:
                self.ax.set_yscale("log", nonpositive="clip")

    class NoDashes(MatplotlibRenderer):
        def _apply(self, artist, item):
            super()._apply(artist, item)
            if isinstance(item, Line):
                artist.set_linestyle("solid")

    class DiamondTooLarge(MatplotlibRenderer):
        def _apply(self, artist, item):
            super()._apply(artist, item)
            if isinstance(item, Markers):
                artist.set_markersize(item.style.size_pt)

    class NoRestacking(MatplotlibRenderer):
        def _reorder(self, order):
            pass

    return {"casing without line": CasingWithoutLine, "autoscale with hidden items": AutoscaleWithHidden,
            "text not upright": NotUpright, "log values clipped": ClipsLogValues, "dashes ignored": NoDashes,
            "diamond too large": DiamondTooLarge, "no restacking": NoRestacking}


MPL_DEFECTS = ["casing without line", "autoscale with hidden items", "text not upright", "log values clipped",
               "dashes ignored", "diamond too large", "no restacking"]


@pytest.mark.parametrize("defect", MPL_DEFECTS)
def test_kit_rejects_matplotlib_defect(defect):
    assert run_conformance(_mpl_factory(_mpl_defects()[defect])) != []
