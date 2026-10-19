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

from coolplot.render.svg import SvgRenderer
from coolplot.render.testing import run_conformance
from coolplot.scene import Text


def _mpl_factory(cls=None):
    pytest.importorskip("matplotlib")
    from coolplot.render.mpl import MatplotlibRenderer
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


class _OffsetIgnored(SvgRenderer):
    def _text(self, item, to_px):
        return super()._text(replace(item, offset_pt=(0.0, 0.0)), to_px)


class _ClipsEverything(SvgRenderer):
    def _open(self, item, extra=""):
        return super()._open(replace(item, clip=True) if isinstance(item, Text) else item, extra)


def _scientific_ticks(text):
    return re.sub(r'(class="cp-tick-label[^"]*"[^>]*data-value="([^"]*)"[^>]*>)[^<]*<',
                  lambda m: m.group(1) + "{0:.2e}".format(float(m.group(2))) + "<", text)


def _shift_lines_up(text):
    """Every line drawn 20 px too high."""
    def shift(match):
        return re.sub(r"([ML]-?[0-9.]+),(-?[0-9.]+)",
                      lambda m: "{0},{1}".format(m.group(1), float(m.group(2)) - 20.0), match.group(0))
    return re.sub(r'class="cp-stroke" d="[^"]*"', shift, text)


class _CirclesOnly(SvgRenderer):
    def _markers(self, item, to_px):
        return super()._markers(replace(item, style=item.style.with_(shape="o")), to_px).replace(
            'data-shape="o"', 'data-shape={0!r}'.format(item.style.shape).replace("'", '"'))


class _JoinedMarkers(SvgRenderer):
    def _markers(self, item, to_px):
        out = super()._markers(item, to_px)
        px, py = to_px(item.x, item.y)
        ok = [(x, y) for x, y in zip(px, py) if math.isfinite(x) and math.isfinite(y)]
        if len(ok) < 2:
            return out
        path = '<path d="M{0},{1}L{2},{3}"/>'.format(ok[0][0], ok[0][1], ok[-1][0], ok[-1][1])
        return out.replace("</g>", path + "</g>", 1) if out.endswith("</g>") else out


def _frame_below_items(text):
    lines = text.split("\n")
    frame = [ln for ln in lines if 'class="cp-frame"' in ln]
    rest = [ln for ln in lines if 'class="cp-frame"' not in ln]
    index = next(i for i, ln in enumerate(rest) if "data-item=" in ln)
    return "\n".join(rest[:index] + frame + rest[index:])


def _vertical_flipped(text):
    return re.sub(r'(data-item="text/vertical-down".*?rotate\()(-?[0-9.]+)',
                  lambda m: m.group(1) + str(-float(m.group(2))), text)


def _no_vertical_grid(text):
    return re.sub(r'<line class="cp-grid-major" x1="([^"]*)" y1="[^"]*" x2="\1"[^>]*/>\n?', "", text)


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
        lambda t: re.sub(r'(class="cp-tick-label[^"]*"[^>]*?font-size=")[^"]*"', r'\g<1>14"', t)),
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
    "text offset ignored": _OffsetIgnored,
    "unclipped text clipped": _ClipsEverything,
    "tick labels not in the central format": _svg_postprocessed(_scientific_ticks),
    "lines drawn too high": _svg_postprocessed(_shift_lines_up),
    "markers shifted sideways": _svg_postprocessed(
        lambda t: re.sub(r'<circle cx="(-?[0-9.]+)"', lambda m: '<circle cx="{0}"'.format(float(m.group(1)) + 8), t)),
    "every marker a circle": _CirclesOnly,
    "markers joined by a line": _JoinedMarkers,
    "frame below the items": _svg_postprocessed(_frame_below_items),
    "vertical text upside down": _svg_postprocessed(_vertical_flipped),
    "grid on one axis only": _svg_postprocessed(_no_vertical_grid),
    "legend text colour ignored": _svg_postprocessed(
        lambda t: re.sub(r'(class="cp-legend-text"[^>]*?fill=")[^"]*"', r'\1#ff0000"', t)),
    "legend background ignored": _svg_postprocessed(
        lambda t: re.sub(r'(class="cp-legend-box"[^>]*?fill=")[^"]*"', r'\1#00ff00"', t)),
    "y ticks too long": _svg_postprocessed(
        lambda t: re.sub(r'(class="cp-tick cp-tick-y" x1="(-?[0-9.]+)" y1="[^"]*" x2=")[^"]*"',
                         lambda m: m.group(1) + str(float(m.group(2)) - 30.0) + '"', t)),
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
    from coolplot.render.mpl import MatplotlibRenderer
    from coolplot.scene import Line, Markers

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

    class OffsetIgnored(MatplotlibRenderer):
        def _apply(self, artist, item):
            super()._apply(artist, item)
            if isinstance(item, Text):
                artist.set_transform(self.ax.transData)

    class ClipsEverything(MatplotlibRenderer):
        def _apply(self, artist, item):
            super()._apply(artist, item)
            artist.set_clip_on(True)

    class DashCapsIgnored(MatplotlibRenderer):
        def _apply(self, artist, item):
            super()._apply(artist, item)
            if isinstance(item, Line):
                artist.set_dash_capstyle("butt")
                artist.set_dash_joinstyle("miter")

    class JoinedMarkers(MatplotlibRenderer):
        def _apply(self, artist, item):
            super()._apply(artist, item)
            if isinstance(item, Markers):
                artist.set_linestyle("-")

    class SceneZOrder(MatplotlibRenderer):
        def _reorder(self, order):
            super()._reorder(order)
            for item_id, artist in self._artists.items():
                artist.set_zorder(1.0 + self._drawn[item_id].z_order)

    class LegendTextBlack(MatplotlibRenderer):
        def _set_legend(self, entries, style):
            super()._set_legend(entries, style)
            legend = self.ax.get_legend()
            if legend is not None:
                for text in legend.get_texts():
                    text.set_color("#000000")

    class OpenFrame(MatplotlibRenderer):
        def _set_axes(self, axes):
            super()._set_axes(axes)
            self.ax.spines["top"].set_visible(False)

    class NoYGrid(MatplotlibRenderer):
        def _set_axes(self, axes):
            super()._set_axes(axes)
            self.ax.yaxis.grid(False)

    class ShiftedData(MatplotlibRenderer):
        def _apply(self, artist, item):
            super()._apply(artist, item)
            if isinstance(item, Line):
                from matplotlib.transforms import ScaledTranslation
                artist.set_transform(self.ax.transData + ScaledTranslation(0.1, 0.0, self.figure.dpi_scale_trans))

    class DefaultTickFormat(MatplotlibRenderer):
        def _set_axes(self, axes):
            super()._set_axes(axes)
            from matplotlib.ticker import LogFormatterSciNotation, ScalarFormatter
            self.ax.yaxis.set_major_formatter(LogFormatterSciNotation() if axes.y_log else ScalarFormatter())

    return {"casing without line": CasingWithoutLine, "autoscale with hidden items": AutoscaleWithHidden,
            "text not upright": NotUpright, "log values clipped": ClipsLogValues, "dashes ignored": NoDashes,
            "diamond too large": DiamondTooLarge, "no restacking": NoRestacking,
            "text offset ignored": OffsetIgnored, "unclipped text clipped": ClipsEverything,
            "default tick format": DefaultTickFormat, "dash caps ignored": DashCapsIgnored,
            "markers joined by a line": JoinedMarkers, "scene z order used directly": SceneZOrder,
            "legend text colour ignored": LegendTextBlack, "frame side missing": OpenFrame,
            "no y grid": NoYGrid, "lines shifted": ShiftedData}


MPL_DEFECTS = ["casing without line", "autoscale with hidden items", "text not upright", "log values clipped",
               "dashes ignored", "diamond too large", "no restacking", "text offset ignored",
               "unclipped text clipped", "default tick format", "dash caps ignored", "markers joined by a line",
               "scene z order used directly", "legend text colour ignored", "frame side missing", "no y grid",
               "lines shifted"]


@pytest.mark.parametrize("defect", MPL_DEFECTS)
def test_kit_rejects_matplotlib_defect(defect):
    assert run_conformance(_mpl_factory(_mpl_defects()[defect])) != []
