# -*- coding: utf-8 -*-
"""The bridge to coolplot-core (``coolplot_core``): the composer and the SVG writer in C++.

``cpp/`` holds coolplot-core, a C++ port of :mod:`coolplot.compose`,
:mod:`coolplot.scene`, :mod:`coolplot.style` and the SVG writer, built as
the nanobind module ``coolplot_core``. When that module can be imported and
the native mode is "on" (:func:`coolplot.core.implementation.set_native_mode`, or the
environment variable ``COOLPLOT_NATIVE=1``), the chart composes its
scene there (:func:`coolplot.compose.compose`) and the SVG renderer
writes its document there. This module sits below both layers. The scene
and the document are the same as from the Python code, point for point
and byte for byte (cpp/tests compares them); the Python modules stay the
reference and do the work when the module is absent.

The records that cross the boundary are those of docs/reference/contracts.md:
the spec, the curve records and the scene, as JSON text.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from .core.implementation import native_mode
from .scene import AxesSpec, axes_from_dict, axes_to_dict, item_from_dict, item_to_dict

try:
    import coolplot_core as _core
except Exception:   # not installed
    _core = None


class CoreRefusal(ValueError):
    """coolplot-core refused a record (its ``coolplot_core.Error``), e.g. a spec it does not know yet."""


class CoreFallbackWarning(RuntimeWarning):
    """The chart was composed in Python because coolplot-core refused its spec.

    The native CI job turns this warning into an error, so that a port that
    refuses charts cannot pass the suite by falling back.
    """


def available() -> bool:
    """Whether the ``coolplot_core`` module is installed."""
    return _core is not None and hasattr(_core, "compose") and hasattr(_core, "scene_to_svg")


def has_pdf() -> bool:
    """Whether the installed ``coolplot_core`` module also writes PDF."""
    return _core is not None and hasattr(_core, "scene_to_pdf") and hasattr(_core, "pdf_plot_size_pt")


def enabled() -> bool:
    """Whether charts are composed and SVG is written by coolplot-core.

    Only when the module is available and the native mode is "on"
    (:func:`coolplot.core.implementation.set_native_mode`, or ``COOLPLOT_NATIVE=1``). In the
    default mode "auto" the Python code does it: from Python it is the
    faster path, because the records cross the boundary as JSON (for a
    p-h chart with labels about 12 ms in C++ against 25 ms in Python, plus
    38 ms for the crossing). The numerics port (:mod:`coolplot.thermo.native`)
    is used unless the mode is "off".
    """
    return available() and native_mode() == "on"


_LONE_SURROGATES = re.compile("[\ud800-\udfff]")


def _clean(data):
    """The record with lone surrogates dropped from every string.

    They are not characters (JSON cannot carry them to the port) and the
    Python writers drop them as well.
    """
    if isinstance(data, str):
        return _LONE_SURROGATES.sub("", data)
    if isinstance(data, dict):
        return {_clean(k): _clean(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_clean(v) for v in data]
    return data


def _dumps(record) -> str:
    return json.dumps(_clean(record), allow_nan=False)


def compose_record(spec, domain, curves, plot_size_pt=None, previous_labels=None, cycles=None) -> dict:
    """The compose record of coolplot-core (cpp/include/coolplot/compose.h) for the composer's arguments."""
    return {
        "spec": spec.to_dict(),
        "domain": {"tp_box": list(domain.tp_box), "ranges_SI": {k: list(v) for k, v in domain.ranges_SI}},
        "curves": [{"request": {"item_id": r.item_id, "key": r.key, "value_SI": r.value_SI, "points": r.points,
                                "labels": r.labels, "anchor_SI": r.anchor_SI},
                    "curve": c.to_dict()} for r, c in curves],
        "cycles": [{"states": {str(n): s.to_dict() for n, s in states.items()},
                    "chains": [[s.to_dict() for s in chain] for chain in chains]} for states, chains in (cycles or ())],
        "plot_size_pt": None if plot_size_pt is None else list(plot_size_pt),
        "previous_labels": None if previous_labels is None else [item_to_dict(t) for t in previous_labels.values()],
    }


def compose(spec, domain, curves, plot_size_pt=None, previous_labels=None, cycles=None):
    """(items, axes) of a chart from coolplot-core, or None when the module is absent.

    The arguments are those of :func:`coolplot.compose.builder.compose`.
    A record the port refuses raises :class:`CoreRefusal`; any other error
    (a bug in the bridge or the port) raises as it is.
    """
    if not available():
        return None
    record = compose_record(spec, domain, curves, plot_size_pt, previous_labels, cycles)
    try:
        text = _core.compose(_dumps(record))
    except _core.Error as error:   # the port's own refusal; anything else is a bug and raises
        raise CoreRefusal(str(error)) from error
    scene = json.loads(text)
    axes = axes_from_dict(scene["axes"])
    return [item_from_dict(d) for d in scene["items"]], axes


def scene_to_svg(axes: Optional[AxesSpec], items, width: int, height: int, margins, id_prefix: str) -> Optional[str]:
    """The SVG document of a scene from coolplot-core, or None when the module is absent.

    ``items`` are the scene's items in scene order (the legend follows it;
    the drawing order is the stable sort by z order); ``margins`` are
    (left, right, top, bottom) in px.
    """
    if not available():
        return None
    scene = {"axes": axes_to_dict(axes or AxesSpec()), "items": [item_to_dict(item) for item in items]}
    left, right, top, bottom = (float(m) for m in margins)
    return _core.scene_to_svg(_dumps(scene), int(width), int(height), (left, right), (top, bottom),
                              _LONE_SURROGATES.sub("", id_prefix))


def scene_to_pdf(axes: Optional[AxesSpec], items, width_pt: float, height_pt: float, margins_pt, font_dirs=(),
                 font_files=(), compress: bool = True) -> Optional[bytes]:
    """The PDF file of a scene from coolplot-core as bytes, or None when the module is absent.

    ``items`` are the scene's items in scene order; ``margins_pt`` are
    (left, right, top, bottom) in points. Fonts come from ``font_files``
    first, then from ``font_dirs`` (the platform's font directories when
    empty); a family without a TrueType file raises ValueError.
    """
    if not has_pdf():
        return None
    scene = {"axes": axes_to_dict(axes or AxesSpec()), "items": [item_to_dict(item) for item in items]}
    left, right, top, bottom = (float(m) for m in margins_pt)
    return _core.scene_to_pdf(_dumps(scene), float(width_pt), float(height_pt), (left, right),
                              (top, bottom), list(font_dirs), list(font_files), bool(compress))


def pdf_plot_size_pt(axes: Optional[AxesSpec], items, width_pt: float, height_pt: float, margins_pt):
    """(width, height) of the plot area of the PDF page in points, or None when the module is absent."""
    if not has_pdf():
        return None
    scene = {"axes": axes_to_dict(axes or AxesSpec()), "items": [item_to_dict(item) for item in items]}
    left, right, top, bottom = (float(m) for m in margins_pt)
    return tuple(_core.pdf_plot_size_pt(_dumps(scene), float(width_pt), float(height_pt), (left, right), (top, bottom)))
