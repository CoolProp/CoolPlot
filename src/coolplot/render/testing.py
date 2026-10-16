# -*- coding: utf-8 -*-
"""Conformance kit for plotting backends.

A backend is accepted when ``run_conformance(factory)`` returns no
failures, where ``factory()`` creates a fresh renderer. The kit draws a
reference scene that uses every style feature, then reads back what the
backend actually drew through ``describe_item`` and ``describe_axes`` and
compares it with what the scene asked for. It then changes the scene step
by step (restyle, hide, restack, reorder, change an item's type, remove,
change axes, grids and legend, autoscale, clear) and checks both the
result and that only the affected items were touched.

docs/backends.md explains each requirement; every failure message ends
with the tag of the section it refers to. Requirements the kit cannot
check are marked "(manual)" there.

Usage in a test suite::

    from coolplot.render.testing import run_conformance
    def test_my_backend():
        assert run_conformance(MyRenderer) == []
"""
from __future__ import annotations

import math
import os
import re
import tempfile
from dataclasses import replace
from typing import Callable, List

import numpy as np

from ..core.numbers import format_number
from ..scene import AxesSpec, Line, Markers, Scene, Text, drawable_limits
from ..style.values import (AxesStyle, Font, GENERIC_FONTS, LegendStyle, LineStyle, MarkerStyle, MARKER_SHAPES,
                     TextStyle, dash_pattern_pt, style_to_dict)

#: Tolerances for read-back numbers. Lengths may be rounded in the output
#: (an SVG keeps three decimals of a pixel), but by no more than 0.005 pt,
#: which is far below anything visible.
REL_TOL = 1e-6
ABS_TOL = 0.005
#: Text angles are compared with this tolerance in degrees.
ANGLE_TOL = 1.0
#: Drawn positions, as fractions of the plot area: 1e-3 is about half a
#: point on a typical plot.
POSITION_TOL = 1e-3

#: Requirements a backend may declare it cannot follow, in
#: ``Renderer.limitations``, because its library offers no way to. The kit
#: then skips exactly those checks; docs/backends.md lists them and every
#: backend documents its own.
ALLOWED_LIMITATIONS = {
    "line_caps": "line caps and joins are the library's own (cap and join are not checked)",
    "text_order": "texts are always drawn above lines and markers (texts and other items are "
                  "each checked for their order among themselves)",
}


# ---------------------------------------------------------------------------
# The reference scene
# ---------------------------------------------------------------------------
def conformance_axes(x_log=False, y_log=True) -> AxesSpec:
    return AxesSpec(
        x_label="Specific enthalpy h / kJ/kg", y_label="Pressure p / bar",
        x_log=x_log, y_log=y_log, x_limits=(0.0, 10.0), y_limits=(0.1, 100.0),
        title="Conformance",
        style=AxesStyle(
            background="#fcfcfb", figure_background="#f9f9f7", frame_color="#c3c2b7",
            frame_width_pt=0.8, tick_color="#c3c2b7", tick_length_pt=4.0, tick_width_pt=0.6,
            tick_direction="out",
            tick_label=TextStyle(font=Font(size_pt=8.0), color="#52514e"),
            axis_label=TextStyle(font=Font(family=("DejaVu Serif", "serif"), size_pt=9.5, style="italic"),
                                 color="#0b0b0b"),
            title=TextStyle(font=Font(size_pt=11.0, weight="bold"), color="#2a78d6"),
            grid_major=LineStyle(color="#e1e0d9", width_pt=0.5, dash="dotted"),
            legend=LegendStyle(location="upper right", background="#fcfcfb",
                               text=TextStyle(font=Font(size_pt=8.0), color="#52514e")),
        ))


def conformance_scene() -> Scene:
    """Items covering every style option, plus awkward data."""
    x = np.linspace(0.5, 9.5, 20)
    items = [
        Line(id="line/solid", role="isoline", group="lines", x=x, y=np.geomspace(0.2, 50.0, 20),
             legend="Solid", style=LineStyle(color="#2a78d6", width_pt=0.75)),
        Line(id="line/dashed", role="isoline", group="lines", x=x, y=np.geomspace(0.3, 60.0, 20),
             legend="Dashed", style=LineStyle(color="#eb6834", width_pt=1.5, dash="dashed")),
        Line(id="line/dotted", role="isoline", group="lines", x=x, y=np.geomspace(0.4, 70.0, 20),
             style=LineStyle(color="#1baf7a", width_pt=0.5, dash="dotted", alpha=0.6, cap="round")),
        Line(id="line/dashdot", role="isoline", group="lines", x=x, y=np.geomspace(0.5, 80.0, 20),
             style=LineStyle(color="#eda100", width_pt=2.0, dash="dashdot", join="bevel", cap="square")),
        Line(id="line/custom", role="process", group="lines", x=x, y=np.geomspace(0.6, 90.0, 20),
             style=LineStyle(color="#0b0b0b", width_pt=2.0, dash=(5.0, 2.0, 1.0, 2.0), alpha=0.7,
                             casing_color="#fcfcfb", casing_width_pt=1.5)),
        # NaN splits a line; non-positive values cannot be shown on a log axis
        Line(id="line/gaps", role="saturation", x=[1.0, 2.0, np.nan, 4.0, 5.0, 6.0, 7.0],
             y=[1.0, 2.0, 3.0, 4.0, -1.0, 0.0, 6.0], z_order=2.0,
             style=LineStyle(color="#52514e", width_pt=1.0)),
        Line(id="line/empty", x=[], y=[]),
        Line(id="line/all-missing", x=[np.nan, np.nan], y=[np.nan, np.nan]),
        Line(id="line/hidden", visible=False, x=x, y=x, style=LineStyle(color="red")),
    ]
    for i, shape in enumerate(sorted(MARKER_SHAPES)):
        hollow = i % 2 == 1
        items.append(Markers(
            id="markers/" + shape, role="state_points", group="markers", z_order=3.0,
            legend="Dashed" if shape == "o" else None,
            x=[1.0 + i, 1.5 + i], y=[5.0, 8.0],
            style=MarkerStyle(shape=shape, size_pt=6.0 + i, face_color=None if hollow else "#0b0b0b",
                              edge_color="#4a3aa7", edge_width_pt=1.0 + 0.25 * i, alpha=0.9)))
    items += [
        Text(id="text/plain", role="annotation", x=5.0, y=1.0, text="plain <&> 'text' \"quoted\" $5 or $6",
             z_order=4.0, style=TextStyle(font=Font(size_pt=9.0), color="#0b0b0b")),
        Text(id="text/styled", role="isoline_label", x=3.0, y=3.0, text="T=25 deg C", z_order=4.0,
             direction=(1.0, 1.0),
             style=TextStyle(font=Font(family=("DejaVu Serif", "serif"), size_pt=7.5, weight="bold",
                                       style="italic"),
                             color="#52514e", alpha=0.8, h_align="left", v_align="bottom",
                             halo_color="#fcfcfb", halo_width_pt=2.0)),
        Text(id="text/down", role="isoline_label", x=7.0, y=30.0, text="falling", z_order=4.0,
             direction=(1.0, -0.5), style=TextStyle(h_align="right", v_align="top")),
        # Leftward directions have to come out upright
        Text(id="text/left-down", x=2.0, y=20.0, text="left down", z_order=4.0, direction=(-1.0, -10.0)),
        Text(id="text/left-up", x=8.0, y=0.5, text="left up", z_order=4.0, direction=(-2.0, 0.1)),
        Text(id="text/nan", x=float("nan"), y=1.0, text="nowhere"),
        # A margin label: shifted on screen and not cut off at the plot area
        Text(id="text/margin", role="isoline_label", x=6.0, y=100.0, text="margin", z_order=4.0,
             offset_pt=(4.0, 6.0), clip=False, style=TextStyle(v_align="bottom")),
        # Straight down and straight up both read from bottom to top
        Text(id="text/vertical-down", x=9.0, y=2.0, text="down", z_order=4.0, direction=(0.0, -1.0)),
        Text(id="text/vertical-up", x=9.5, y=2.0, text="up", z_order=4.0, direction=(0.0, 1.0)),
        # A huge z order still stays below the frame and the legend
        Line(id="line/on-top", role="process", x=[0.2, 9.8], y=[0.15, 95.0], z_order=1e12,
             style=LineStyle(color="#4a3aa7", width_pt=1.0)),
    ]
    return Scene(conformance_axes(), items)


# ---------------------------------------------------------------------------
# What the backend should report
# ---------------------------------------------------------------------------
def _ok_mask(x, y, axes: AxesSpec):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    if axes.x_log:
        ok &= x > 0.0
    if axes.y_log:
        ok &= y > 0.0
    return ok


def _sample_colors(item):
    """Colours a legend sample of this item shows: line colour or marker edge (else face)."""
    if isinstance(item, Line):
        return {item.style.color} - {None}
    if isinstance(item, Markers):
        return {item.style.edge_color or item.style.face_color} - {None}
    return set()


def safe_limits(limits, log):
    """The limits a backend has to use, see :func:`coolplot.scene.drawable_limits`."""
    return drawable_limits(limits, log)


def expected_item(item, axes: AxesSpec) -> dict:
    """The normalised description a conforming backend reports for ``item``."""
    out = {"visible": item.visible, "clip": getattr(item, "clip", True)}
    s = item.style
    if isinstance(item, Line):
        cased = s.casing_color is not None and s.casing_width_pt > 0.0
        out.update(kind="line", color=s.color, alpha=s.alpha, width_pt=s.width_pt,
                   dash_pt=dash_pattern_pt(s.dash, s.width_pt), cap=s.cap, join=s.join,
                   casing_color=s.casing_color if cased else None,
                   casing_width_pt=s.casing_width_pt if cased else 0.0,
                   n_points=int(np.sum(_ok_mask(item.x, item.y, axes))))
        if cased:
            out.update(casing_dash_pt=dash_pattern_pt(s.dash, s.width_pt), casing_alpha=s.alpha)
    elif isinstance(item, Markers):
        has_face = item.style.shape not in ("x", "+")
        out.update(kind="markers", shape=s.shape, size_pt=s.size_pt,
                   face_color=s.face_color if has_face else None,
                   edge_color=s.edge_color, edge_width_pt=s.edge_width_pt, alpha=s.alpha,
                   n_points=int(np.sum(_ok_mask(item.x, item.y, axes))), connected=False)
    elif isinstance(item, Text):
        drawable = math.isfinite(item.x) and math.isfinite(item.y)
        out.update(kind="text", text=item.text, font_family=tuple(s.font.family),
                   font_size_pt=s.font.size_pt, font_weight=s.font.weight, font_style=s.font.style,
                   color=s.color, alpha=s.alpha, h_align=s.h_align, v_align=s.v_align,
                   halo_color=s.halo_color if s.halo_width_pt > 0 else None,
                   halo_width_pt=s.halo_width_pt if s.halo_color else 0.0, offset_pt=item.offset_pt)
        if not drawable:
            out["visible"] = False
    return out


def _font_keys(prefix, style: TextStyle, full=True) -> dict:
    out = {prefix + "_font_family": tuple(style.font.family),
           prefix + "_font_size_pt": style.font.size_pt, prefix + "_color": style.color}
    if full:
        out.update({prefix + "_font_weight": style.font.weight, prefix + "_font_style": style.font.style})
    return out


def expected_axes(scene: Scene, owns_canvas: bool) -> dict:
    a = scene.axes
    st = a.style
    legend_shown = bool(st.legend.visible and scene.legend_entries())
    grid_major = _painted(st.grid_major)
    grid_minor = _painted(st.grid_minor)
    out = dict(x_label=a.x_label, y_label=a.y_label, x_log=a.x_log, y_log=a.y_log, title=a.title,
               background=st.background, frame_color=st.frame_color,
               frame_width_pt=st.frame_width_pt, tick_direction=st.tick_direction,
               tick_color=st.tick_color, tick_length_pt=st.tick_length_pt, tick_width_pt=st.tick_width_pt,
               y_tick_direction=st.tick_direction, y_tick_color=st.tick_color,
               y_tick_length_pt=st.tick_length_pt, y_tick_width_pt=st.tick_width_pt,
               grid_color=grid_major.color if grid_major is not None else None,
               grid_minor_color=grid_minor.color if grid_minor is not None else None,
               items_below_frame=True,
               legend=[(text, tuple(sorted(set().union(*(_sample_colors(i) for i in items)))))
                       for text, items in scene.legend_entries()] if legend_shown else [])
    if st.frame_color is not None and st.frame_width_pt > 0.0:
        out["frame_sides"] = 4
    for name, limits, log in (("x_limits", a.x_limits, a.x_log), ("y_limits", a.y_limits, a.y_log)):
        if limits is not None:
            out[name] = safe_limits(limits, log)
    if grid_major is not None:
        g = grid_major
        out.update(grid_width_pt=g.width_pt, grid_dash_pt=dash_pattern_pt(g.dash, g.width_pt),
                   grid_below_items=True)
    if legend_shown:
        out["legend_location"] = st.legend.location
        out["items_below_legend"] = True
        out["legend_background"] = st.legend.background
        out.update(_font_keys("legend", st.legend.text, full=False))
    if owns_canvas:
        out["figure_background"] = st.figure_background
    out.update(_font_keys("x_label", st.axis_label))
    out.update(_font_keys("y_label", st.axis_label))
    if a.title:
        out.update(_font_keys("title", st.title))   # nothing to read back without a title
    out.update(_font_keys("tick_label", st.tick_label, full=False))
    return out


def _painted(grid):
    """A grid level that is drawn: set and with a colour."""
    return grid if grid is not None and grid.color is not None else None


def _frac(v, lo, hi, log):
    if log:
        return (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))
    return (v - lo) / (hi - lo)


def expected_points(item, axes: AxesSpec, plot_size_pt, limits):
    """Where the points of an item belong, as fractions of the plot area (y up)."""
    (x0, x1), (y0, y1) = limits
    if isinstance(item, Text):
        width, height = plot_size_pt
        return [(_frac(item.x, x0, x1, axes.x_log) + item.offset_pt[0] / width,
                 _frac(item.y, y0, y1, axes.y_log) + item.offset_pt[1] / height)]
    ok = _ok_mask(item.x, item.y, axes)
    return [(_frac(x, x0, x1, axes.x_log), _frac(y, y0, y1, axes.y_log))
            for x, y in zip(np.asarray(item.x, dtype=float)[ok], np.asarray(item.y, dtype=float)[ok])]


def expected_screen_angle(item: Text, axes: AxesSpec, plot_size_pt, limits) -> float:
    """Counter-clockwise screen angle of a direction given in data coordinates, kept upright."""
    if item.direction is None:
        return 0.0
    (x0, x1), (y0, y1) = limits
    width, height = plot_size_pt

    def frac(v, lo, hi, log):
        if log:
            return (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))
        return (v - lo) / (hi - lo)

    dx, dy = item.direction
    eps = 1e-6
    fx = frac(item.x + dx * eps, x0, x1, axes.x_log) - frac(item.x, x0, x1, axes.x_log)
    fy = frac(item.y + dy * eps, y0, y1, axes.y_log) - frac(item.y, y0, y1, axes.y_log)
    angle = math.degrees(math.atan2(fy * height, fx * width))
    if angle > 90.0:
        angle -= 180.0
    elif angle <= -90.0:
        angle += 180.0
    return angle


def _same(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, float) or isinstance(b, float):
        if a is None or b is None:
            return a is b
        return math.isclose(float(a), float(b), rel_tol=REL_TOL, abs_tol=ABS_TOL)
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def _fonts_ok(requested, reported) -> bool:
    """A backend may drop fonts that are not installed, but must keep the
    order and the generic fallback ("sans-serif", ...) at the end."""
    reported = list(reported or ())
    if not reported:
        return False
    it = iter(requested)
    if not all(any(r == q for q in it) for r in reported):
        return False
    generic = [f for f in requested if f in GENERIC_FONTS]
    return not generic or reported[-1] == generic[-1]


def _compare(where: str, expected: dict, actual: dict, failures: List[str]):
    for key, want in expected.items():
        if key not in actual:
            failures.append("{0}: backend does not report '{1}' [read-back]".format(where, key))
        elif key.endswith("font_family"):
            if not _fonts_ok(want, actual[key]):
                failures.append("{0}: {1} {2!r} does not honour {3!r} [style]".format(
                    where, key, actual[key], want))
        elif not _same(want, actual[key]):
            failures.append("{0}: {1} is {2!r}, expected {3!r} [style]".format(where, key, actual[key], want))


def _check_scene(renderer, scene: Scene, failures: List[str], label: str):
    try:
        axes_actual = renderer.describe_axes()
    except Exception as e:
        failures.append("{0}: describe_axes failed: {1!r} [read-back]".format(label, e))
        return
    owns = bool(getattr(renderer, "owns_canvas", True))
    _compare(label + ": axes", expected_axes(scene, owns), axes_actual, failures)
    if _painted(scene.axes.style.grid_major) is not None:
        for name in ("x_grid_lines", "y_grid_lines"):
            if axes_actual.get(name, 0) < 2:
                failures.append("{0}: only {1} major grid lines on the {2} axis [style]".format(
                    label, axes_actual.get(name), name[0]))
    for name, limits in (("x_limits", scene.axes.x_limits), ("y_limits", scene.axes.y_limits)):
        if limits is not None and limits[0] == limits[1]:
            lo, hi = axes_actual.get(name, (None, None))
            if lo is None or not lo < limits[0] < hi:
                failures.append("{0}: equal {1} {2} drawn as {3} [robustness]".format(
                    label, name, limits, (lo, hi)))
    if "plot_size_pt" not in axes_actual:
        failures.append("{0}: backend does not report 'plot_size_pt' [read-back]".format(label))
    for name in ("x", "y"):
        labels = axes_actual.get(name + "_tick_labels")
        if labels is None:
            failures.append("{0}: backend does not report '{1}_tick_labels' [read-back]".format(label, name))
        elif not labels:
            failures.append("{0}: no {1} tick labels [number format]".format(label, name))
        else:
            for value, text in labels:
                want = format_number(value, scene.axes.tick_digits)
                if text != want:
                    failures.append("{0}: {1} tick label {2!r} at {3!r}, expected {4!r} [number format]".format(
                        label, name, text, value, want))
                    break

    limitations = set(getattr(renderer, "limitations", ()))
    unknown = limitations - set(ALLOWED_LIMITATIONS)
    if unknown:
        failures.append("{0}: unknown limitations {1} [limitations]".format(label, sorted(unknown)))
    visible_order = [i for i in scene.draw_order() if expected_item(scene[i], scene.axes)["visible"]]
    if "text_order" in limitations:
        texts = [i for i in visible_order if isinstance(scene[i], Text)]
        others = [i for i in visible_order if not isinstance(scene[i], Text)]
    for item in scene:
        where = "{0}: {1}".format(label, item.id)
        try:
            actual = renderer.describe_item(item.id)
        except Exception as e:
            failures.append("{0}: describe_item failed: {1!r} [read-back]".format(where, e))
            continue
        want = expected_item(item, scene.axes)
        if not want["visible"]:
            if actual.get("visible"):
                failures.append("{0}: should not be visible [visibility]".format(where))
            continue
        if "line_caps" in limitations:
            want.pop("cap", None)
            want.pop("join", None)
        _compare(where, want, actual, failures)
        order = visible_order
        if "text_order" in limitations:
            order = texts if isinstance(item, Text) else others
        if actual.get("draw_rank") != order.index(item.id):
            failures.append("{0}: drawn at rank {1}, expected {2} [order]".format(
                where, actual.get("draw_rank"), order.index(item.id)))
        if "plot_size_pt" not in axes_actual:
            continue
        limits = (axes_actual.get("x_limits"), axes_actual.get("y_limits"))
        if want["kind"] == "text":
            angle = actual.get("screen_angle_deg")
            target = expected_screen_angle(item, scene.axes, axes_actual["plot_size_pt"], limits)
            if angle is None or not math.isfinite(angle) or abs(angle - target) > ANGLE_TOL:
                failures.append("{0}: drawn at {1} deg, expected {2:.2f} deg [text direction]".format(
                    where, angle, target))
        _check_positions(where, item, scene.axes, axes_actual["plot_size_pt"], limits, actual, failures)


def _check_positions(where, item, axes, plot_size_pt, limits, actual, failures):
    """Drawn points against where they belong, within POSITION_TOL of the plot size."""
    drawn = actual.get("drawn_points")
    if drawn is None:
        failures.append("{0}: backend does not report 'drawn_points' [read-back]".format(where))
        return
    want = expected_points(item, axes, plot_size_pt, limits)
    if len(drawn) != len(want):
        failures.append("{0}: {1} points drawn, expected {2} [position]".format(where, len(drawn), len(want)))
        return
    for (fx, fy), (ex, ey) in zip(drawn, want):
        if not (abs(fx - ex) <= POSITION_TOL and abs(fy - ey) <= POSITION_TOL):
            failures.append("{0}: point drawn at {1}, expected {2} (fractions of the plot area) "
                            "[position]".format(where, (round(fx, 4), round(fy, 4)), (round(ex, 4), round(ey, 4))))
            return


# ---------------------------------------------------------------------------
# The kit
# ---------------------------------------------------------------------------
def run_conformance(factory: Callable[[], object]) -> List[str]:
    """Run every check against fresh renderers from ``factory``; returns failures."""
    failures: List[str] = []
    renderer = factory()
    scene = conformance_scene()

    # 1. First draw: everything added, everything styled as asked
    try:
        report = renderer.sync(scene)
    except Exception as e:
        return ["first sync raised {0!r} [robustness]".format(e)]
    if sorted(report.added) != sorted(scene.ids()):
        failures.append("first sync did not report all items as added [sync report]")
    _check_scene(renderer, scene, failures, "initial")

    # 2. Nothing changed: nothing touched
    report = renderer.sync(scene)
    if report.changed:
        failures.append("second sync of an unchanged scene changed something [selective update]")

    # 3. Restyle one line
    obj_before = _backend_object(renderer, "line/solid")
    other_before = _backend_object(renderer, "line/dashed")
    old = scene["line/solid"]
    scene.put(replace(old, style=old.style.with_(color="#e34948", dash="dotted", width_pt=1.25)))
    report = renderer.sync(scene)
    if report.updated != ["line/solid"] or report.added or report.removed:
        failures.append("restyling one line reported {0} [selective update]".format(report))
    if "in_place_updates" in getattr(renderer, "capabilities", ()):
        if obj_before is not None and _backend_object(renderer, "line/solid") is not obj_before:
            failures.append("restyled line got a new backend object [in-place update]")
        if other_before is not None and _backend_object(renderer, "line/dashed") is not other_before:
            failures.append("an untouched line got a new backend object [selective update]")
    _check_scene(renderer, scene, failures, "restyled")

    # 4. Hide, restack, move data, minor grid
    scene.put(replace(scene["markers/o"], visible=False))
    scene.put(replace(scene["line/dotted"], z_order=10.0))
    scene.put(replace(scene["line/dashed"], y=np.geomspace(1.0, 99.0, 20)))
    scene.set_axes(replace(scene.axes, style=replace(
        scene.axes.style, grid_minor=LineStyle(color="#f0efec", width_pt=0.3))))
    renderer.sync(scene)
    _check_scene(renderer, scene, failures, "hidden+restacked")

    # 5. Same z order, new scene order: drawing order follows the scene
    items = list(scene)
    scene.replace_all([items[1], items[0]] + items[2:])
    report = renderer.sync(scene)
    if not report.reordered:
        failures.append("swapping two items of equal z order was not reported as reordered [order]")
    _check_scene(renderer, scene, failures, "reordered")

    # 6. An item changes its type under the same id
    first = list(scene)[0]
    scene.put(Markers(id=first.id, x=[2.0, 3.0], y=[2.0, 3.0], z_order=first.z_order))
    renderer.sync(scene)
    _check_scene(renderer, scene, failures, "type change")

    # 7. Remove an item, change the axes and the legend
    scene.remove("line/custom")
    scene.set_axes(replace(scene.axes, x_log=True, y_log=False, x_limits=(0.5, 20.0),
                           y_limits=(-5.0, 120.0), title="Changed",
                           style=replace(scene.axes.style, grid_major=None, grid_minor=None,
                                         tick_direction="in",
                                         legend=replace(scene.axes.style.legend, location="lower left"))))
    report = renderer.sync(scene)
    if report.removed != ["line/custom"]:
        failures.append("removal reported {0} [sync report]".format(report.removed))
    try:
        renderer.describe_item("line/custom")
        failures.append("a removed item is still described [removal]")
    except KeyError:
        pass
    except Exception as e:
        failures.append("describe_item of a removed item raised {0!r} instead of KeyError [read-back]".format(e))
    _check_scene(renderer, scene, failures, "new axes")

    for location in ("upper left", "lower right", "outside right"):
        scene.set_axes(replace(scene.axes, style=replace(scene.axes.style, legend=replace(
            scene.axes.style.legend, location=location))))
        renderer.sync(scene)
        _check_scene(renderer, scene, failures, "legend " + location)

    scene.set_axes(replace(scene.axes, style=replace(scene.axes.style, legend=replace(
        scene.axes.style.legend, visible=False))))
    renderer.sync(scene)
    _check_scene(renderer, scene, failures, "legend off")

    # 8. Clear and draw again
    renderer.clear()
    for item_id in scene.ids():
        try:
            renderer.describe_item(item_id)
            failures.append("{0} survived clear() [clear]".format(item_id))
            break
        except KeyError:
            pass
    report = renderer.sync(scene)
    if sorted(report.added) != sorted(scene.ids()):
        failures.append("sync after clear() did not add everything [clear]")
    _check_scene(renderer, scene, failures, "after clear")

    # 9. Log axis with a lower limit at zero, and autoscaling
    failures.extend(_check_limits(factory))

    # 10. Awkward but valid axes: no title, a grid without colour, equal limits
    scene = conformance_scene()
    scene.set_axes(replace(scene.axes, title="", x_limits=(5.0, 5.0),
                           style=replace(scene.axes.style, grid_major=LineStyle(color=None))))
    renderer = factory()
    try:
        renderer.sync(scene)
        _check_scene(renderer, scene, failures, "awkward axes")
    except Exception as e:
        failures.append("awkward axes raised {0!r} [robustness]".format(e))

    # 11. Events, for backends that produce them
    if "events" in getattr(renderer, "capabilities", ()):
        failures.extend(check_events(factory))

    # 12. File output: valid, ASCII, no NaN, deterministic
    if "file_output" in getattr(renderer, "capabilities", ()):
        failures.extend(_check_file_output(factory))

    # 13. PDF: fonts, texts, colours, title, reproducible
    if "pdf_output" in getattr(renderer, "capabilities", ()):
        failures.extend(check_pdf(factory))
    return failures


def _backend_object(renderer, item_id):
    getter = getattr(renderer, "backend_object", None)
    return getter(item_id) if getter is not None else None


def _check_limits(factory) -> List[str]:
    failures = []
    # A log axis cannot start at zero: the backend uses upper / 1000
    scene = conformance_scene()
    scene.set_axes(replace(scene.axes, y_limits=(0.0, 100.0)))
    renderer = factory()
    renderer.sync(scene)
    _check_scene(renderer, scene, failures, "log limit at zero")

    # Autoscale covers visible data only
    scene = Scene(AxesSpec(y_log=True), [
        Line(id="a", x=[1.0, 2.0, 3.0], y=[0.5, 5.0, 50.0]),
        Markers(id="b", x=[4.0], y=[np.nan]),
        Line(id="hidden", visible=False, x=[-100.0, 1000.0], y=[1e-6, 1e9]),
    ])
    renderer = factory()
    renderer.sync(scene)
    (x_lo, x_hi), (y_lo, y_hi) = renderer.describe_axes()["x_limits"], renderer.describe_axes()["y_limits"]
    if not (x_lo <= 1.0 and x_hi >= 3.0 and y_lo <= 0.5 and y_hi >= 50.0):
        failures.append("autoscaled limits {0} do not cover the visible data [robustness]".format(
            ((x_lo, x_hi), (y_lo, y_hi))))
    if x_hi >= 1000.0 or x_lo <= -100.0 or y_hi >= 1e9 or y_lo <= 1e-6 or not y_lo > 0.0:
        failures.append("autoscaled limits {0} include hidden items or non-positive log values "
                        "[robustness]".format(((x_lo, x_hi), (y_lo, y_hi))))
    # A single point: the span is padded, never zero
    scene = Scene(AxesSpec(), [Markers(id="p", x=[2.0], y=[3.0])])
    renderer = factory()
    renderer.sync(scene)
    (x_lo, x_hi), (y_lo, y_hi) = renderer.describe_axes()["x_limits"], renderer.describe_axes()["y_limits"]
    if not (x_lo < 2.0 < x_hi and y_lo < 3.0 < y_hi):
        failures.append("a single point gave limits {0} [robustness]".format(((x_lo, x_hi), (y_lo, y_hi))))
    return failures


def _check_file_output(factory) -> List[str]:
    failures = []
    outputs = []
    for _ in range(2):
        renderer = factory()
        renderer.sync(conformance_scene())
        suffix = getattr(renderer, "default_suffix", ".out")
        handle, path = tempfile.mkstemp(suffix=suffix)
        os.close(handle)
        try:
            renderer.save(path)
            with open(path, "rb") as f:
                outputs.append(f.read())
        finally:
            os.remove(path)
    if not outputs[0]:
        failures.append("save() wrote an empty file [file output]")
    if outputs[0] != outputs[1]:
        failures.append("the same scene gave different files [deterministic output]")
    if getattr(factory(), "text_output", False):
        try:
            text = outputs[0].decode("ascii")
        except UnicodeDecodeError:
            return failures + ["text output is not ASCII [file output]"]
        if re.search(r"(?<![A-Za-z_/-])nan(?![A-Za-z])", text, re.IGNORECASE):
            failures.append("text output contains 'nan' [robustness]")
    return failures


def _scene_colors(scene: Scene) -> set:
    """Every "#rrggbb" colour the styles of a scene name (visible items, axes, legend)."""
    found = set()

    def walk(value):
        if isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                walk(v)
        elif isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            found.add(value.lower())
    styles = [item.style for item in scene if item.visible and getattr(item, "style", None) is not None]
    for style in styles + [scene.axes.style]:
        walk(style_to_dict(style))
    return found


def _close_color(color: str, palette: set) -> bool:
    """True if a colour is in the palette, within rounding to 1/255 per channel."""
    rgb = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    return any(all(abs(a - int(p[i:i + 2], 16)) <= 1 for a, i in zip(rgb, (1, 3, 5))) for p in palette)


def _scene_texts(scene: Scene) -> set:
    """Texts a PDF of the scene has to contain, word for word."""
    texts = {item.text for item in scene if isinstance(item, Text) and item.visible
             and math.isfinite(item.x) and math.isfinite(item.y) and item.text.strip()}
    axes = scene.axes
    texts |= {t for t in (axes.title, axes.x_label, axes.y_label) if t}
    if axes.style.legend.visible:
        texts |= {item.legend for item in scene if item.visible and item.legend}
    return texts


def check_pdf(factory) -> List[str]:
    """Check the PDF of a backend with the "pdf_output" capability.

    The file is read back with :mod:`coolplot.render.pdf_reader`: every
    font is embedded as TrueType or Type 1 and matches its declared type,
    every text of the scene is in the file as written (no math markup,
    nothing lost), only colours of the scene's styles paint, the title is
    the document title, and the same scene gives the same file.
    """
    from .pdf_reader import read_pdf
    failures = []
    scene = conformance_scene()
    folder = tempfile.mkdtemp()
    try:
        outputs = []
        for name in ("a.pdf", "b.pdf"):
            renderer = factory()
            renderer.sync(scene)
            path = os.path.join(folder, name)
            renderer.save(path)
            with open(path, "rb") as f:
                outputs.append(f.read())
        try:
            content = read_pdf(os.path.join(folder, "a.pdf"))
        except Exception as e:
            return ["the PDF could not be read back: {0!r} [pdf]".format(e)]
    finally:
        for name in os.listdir(folder):
            os.remove(os.path.join(folder, name))
        os.rmdir(folder)
    if outputs[0] != outputs[1]:
        failures.append("the same scene gave different PDF files [pdf]")
    if content.pages != 1:
        failures.append("the PDF has {0} pages, expected 1 [pdf]".format(content.pages))
    if not content.fonts:
        failures.append("the PDF has no fonts, so its texts are not text [pdf]")
    for font in content.fonts:
        for problem in font.problems:
            failures.append("PDF font {0}: {1} [pdf]".format(font.name, problem))
    found = {" ".join(t.split()) for t in content.texts}
    for text in sorted(_scene_texts(scene)):
        if " ".join(text.split()) not in found:
            failures.append("PDF lacks the text {0!r} as written [pdf]".format(text))
    palette = _scene_colors(scene)
    for color in sorted(content.colors):
        if not _close_color(color, palette):
            failures.append("PDF paints with {0}, a colour no style asked for [pdf]".format(color))
    if scene.axes.title and content.info.get("Title") != scene.axes.title:
        failures.append("PDF title is {0!r}, expected {1!r} [pdf]".format(content.info.get("Title"),
                                                                          scene.axes.title))
    return failures


def _events_scene() -> Scene:
    return Scene(AxesSpec(x_limits=(0.0, 10.0), y_limits=(0.0, 10.0)), [
        Line(id="line", x=[0.0, 10.0], y=[5.0, 5.0], z_order=1.0),
        Markers(id="states", x=[2.0, 8.0], y=[5.0, 5.0], z_order=6.0),
    ])


def check_events(factory) -> List[str]:
    """Events in display units, from simulated input [events].

    A backend with the "events" capability provides
    ``simulate_pointer(kind, x, y)`` ("move", "press", "release") and
    ``simulate_view(x_limits, y_limits)``, which feed input through the same
    path as real input.
    """
    from ..core.events import Click, Drag, DragEnd, DragStart, Hover, ViewChanged
    failures: List[str] = []
    renderer = factory()
    for name in ("simulate_pointer", "simulate_view"):
        if not callable(getattr(renderer, name, None)):
            return ["a backend with events has to provide {0}() [events]".format(name)]
    scene = _events_scene()
    renderer.sync(scene)
    events = []
    token = renderer.connect(events.append)
    tol = 0.02   # in data units on a 0 to 10 axis: about a pixel

    def close(event, x, y):
        return abs(event.x - x) <= tol * 10 and abs(event.y - y) <= tol * 10

    def take():
        out = list(events)
        events.clear()
        return out

    renderer.simulate_pointer("move", 8.0, 5.0)
    got = take()
    if not (len(got) == 1 and isinstance(got[0], Hover) and got[0].item_id == "states" and got[0].index == 1
            and close(got[0], 8.0, 5.0)):
        failures.append("hover on the second marker (above a line) gave {0} [events]".format(got))
    renderer.simulate_pointer("move", 5.0, 5.0)
    got = take()
    if not (len(got) == 1 and isinstance(got[0], Hover) and got[0].item_id == "line"):
        failures.append("hover on the line gave {0} [events]".format(got))
    renderer.simulate_pointer("move", 5.0, 9.0)
    got = take()
    if not (len(got) == 1 and isinstance(got[0], Hover) and got[0].item_id is None and close(got[0], 5.0, 9.0)):
        failures.append("hover on empty space gave {0} [events]".format(got))

    renderer.simulate_pointer("press", 2.0, 5.0)
    renderer.simulate_pointer("move", 3.0, 6.0)
    renderer.simulate_pointer("move", 4.0, 7.0)
    renderer.simulate_pointer("release", 4.0, 7.0)
    got = take()
    kinds = [type(e).__name__ for e in got]
    if not (kinds and kinds[0] == "DragStart" and kinds[-1] == "DragEnd" and "Drag" in kinds
            and all(getattr(e, "item_id", None) == "states" and e.index == 0 for e in got)
            and close(got[-1], 4.0, 7.0)):
        failures.append("dragging the first marker gave {0} [events]".format(got))
    elif not isinstance(got[0], DragStart) or not any(isinstance(e, Drag) for e in got) \
            or not isinstance(got[-1], DragEnd):
        failures.append("drag events of the wrong types: {0} [events]".format(kinds))

    renderer.simulate_pointer("press", 5.0, 9.0)
    renderer.simulate_pointer("release", 5.0, 9.0)
    got = take()
    if not (len(got) == 1 and isinstance(got[0], Click) and got[0].item_id is None and close(got[0], 5.0, 9.0)):
        failures.append("a click on empty space gave {0} [events]".format(got))

    renderer.simulate_view((1.0, 9.0), (2.0, 8.0))
    got = [e for e in take() if isinstance(e, ViewChanged)]
    if not got or not (_same(got[-1].x_limits, (1.0, 9.0)) and _same(got[-1].y_limits, (2.0, 8.0))):
        failures.append("zooming gave {0} [events]".format(got))

    # Limits set by sync are the application's own, not a user event
    scene.set_axes(replace(scene.axes, x_limits=(0.0, 20.0)))
    renderer.sync(scene)
    got = [e for e in take() if isinstance(e, ViewChanged)]
    if got:
        failures.append("sync with new limits reported {0} as a user event [events]".format(got))

    renderer.disconnect(token)
    renderer.simulate_pointer("move", 5.0, 9.0)
    if events:
        failures.append("events arrived after disconnect [events]")
    return failures
