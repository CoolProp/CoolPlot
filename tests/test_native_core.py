# -*- coding: utf-8 -*-
"""coolplot-core (cpp/) through its Python module, against the Python reference.

These tests run only when ``coolplot_core`` is installed (built from cpp/
with -DCOOLPLOT_CORE_PYTHON=ON); without it they are skipped, in CI too.
"""
import json
import math

import pytest

from coolplot import corelib as native
from coolplot.compose.builder import compose as compose_python
from coolplot.core.floats import same_numbers
from coolplot.scene import Scene, items_equal
from coolplot.testing import conformance_scene, run_conformance

needs_core = pytest.mark.skipif(not native.available(), reason="coolplot_core is not installed")


def _charts():
    pytest.importorskip("CoolProp")
    from coolplot import PropertyDiagram, PsychrometricChart
    diagram = PropertyDiagram("R290", "ph", tp_limits="ACHP", settings="interactive")
    diagram.set_default_lines(labels=True)
    diagram.add_cycle("heat pump", [{"p": 3.0, "T": 0.0}, {"p": 15.0, "via": "compression", "eta_is": 0.7},
                                    {"p": 15.0, "Q": 0.0}, {"p": 3.0, "via": "isenthalpic"}])
    margin = PropertyDiagram("HEOS::R32[0.7]&R125[0.3]", "Ts", tp_limits="ACHP", settings="print")
    margin.settings = margin.settings.with_(calc="interactive", labels={"mode": "margin"})
    margin.set_default_lines(labels=True)
    chart = PsychrometricChart(T_range=(-10, 45), W_range=(0, 25), settings="interactive")
    chart.set_default_lines()
    chart.add_cycle("Air conditioning", [{"T": 32, "RH": 50}, {"T": 13, "RH": 95}, {"T": 20, "W": 8.9}], closed=False)
    return [diagram, margin, chart]


def _both_scenes(chart):
    """(Python scene, native scene) of a chart from the same curves."""
    from coolplot.engine import plan
    spec = chart.spec
    domain = chart.engine.domain(spec)
    curves = chart.engine.curves(spec, domain, plan(spec, domain))
    cycles = [chart.engine.cycle(spec, c) for c in spec.cycles]
    items, axes = compose_python(spec, domain, curves, None, None, cycles)
    native_items, native_axes = native.compose(spec, domain, curves, None, None, cycles)
    return Scene(axes, items), Scene(native_axes, native_items)


def _same(a, b, path=""):
    """Plain data compared with numbers within 1e-9 relative; returns the first difference."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if a is None or b is None:
            return "" if a is b else path
        return "" if math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12) else "{0}: {1} vs {2}".format(path, a, b)
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return "{0}: keys {1} vs {2}".format(path, sorted(set(a) ^ set(b)), "")
        for k in a:
            d = _same(a[k], b[k], path + "." + str(k))
            if d:
                return d
        return ""
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return "{0}: {1} vs {2} entries".format(path, len(a), len(b))
        for i, (x, y) in enumerate(zip(a, b)):
            d = _same(x, y, "{0}[{1}]".format(path, i))
            if d:
                return d
        return ""
    return "" if a == b else "{0}: {1!r} vs {2!r}".format(path, a, b)


def test_the_switch(monkeypatch):
    from coolplot import native_mode, set_native_mode
    from coolplot.thermo import native as numerics
    monkeypatch.setenv("COOLPLOT_NATIVE", "0")
    assert not native.enabled() and not numerics.enabled() and native_mode() == "off"
    monkeypatch.setenv("COOLPLOT_NATIVE", "1")
    assert native.enabled() == native.available() and native_mode() == "on"
    assert numerics.enabled() == numerics.available()
    # Unset (or "auto"), the Python composer and writer do the work (faster
    # from Python) and the numerics port computes the lines
    for value in (None, "auto", " AUTO "):
        if value is None:
            monkeypatch.delenv("COOLPLOT_NATIVE")
        else:
            monkeypatch.setenv("COOLPLOT_NATIVE", value)
        assert native_mode() == "auto" and not native.enabled()
        assert numerics.enabled() == numerics.available()
    # The setting overrides the environment variable until it is reset with None
    monkeypatch.setenv("COOLPLOT_NATIVE", "0")
    assert set_native_mode("on") is None   # the environment variable decided before
    assert native_mode() == "on" and native.enabled() == native.available()
    assert set_native_mode("Auto") == "on" and native_mode() == "auto"
    assert set_native_mode(None) == "auto" and native_mode() == "off"
    with pytest.raises(ValueError, match="expected one of"):
        set_native_mode("fast")
    assert native_mode() == "off"
    # Passing the returned value back restores what was there, here the environment
    previous = set_native_mode("on")
    set_native_mode(previous)
    monkeypatch.setenv("COOLPLOT_NATIVE", "1")
    assert native_mode() == "on"


def test_compose_falls_back_without_the_module(monkeypatch):
    from coolplot.compose import compose
    from coolplot.engine import plan
    monkeypatch.setattr(native, "available", lambda: False)
    monkeypatch.setenv("COOLPLOT_NATIVE", "1")
    assert native.compose(None, None, []) is None and not native.enabled()
    # The package entry point then composes in Python
    chart = _charts()[0]
    spec = chart.spec
    domain = chart.engine.domain(spec)
    curves = chart.engine.curves(spec, domain, plan(spec, domain))
    items, axes = compose(spec, domain, curves)
    reference, reference_axes = compose_python(spec, domain, curves)
    assert [i.id for i in items] == [i.id for i in reference] and axes == reference_axes


@needs_core
def test_compose_falls_back_with_a_warning_when_the_port_refuses(monkeypatch):
    from coolplot.compose import compose
    from coolplot.engine import plan
    chart = _charts()[0]
    spec = chart.spec
    domain = chart.engine.domain(spec)
    curves = chart.engine.curves(spec, domain, plan(spec, domain))

    def refuse(*args):
        raise native.CoreRefusal("something new")
    monkeypatch.setenv("COOLPLOT_NATIVE", "1")
    monkeypatch.setattr(native, "compose", refuse)
    with pytest.warns(native.CoreFallbackWarning, match="something new"):
        items, _ = compose(spec, domain, curves)
    assert [i.id for i in items] == [i.id for i in compose_python(spec, domain, curves)[0]]

    # Any other error is a bug and is not hidden by the fallback
    def broken(*args):
        raise ValueError("a bug")
    monkeypatch.setattr(native, "compose", broken)
    with pytest.raises(ValueError, match="a bug"):
        compose(spec, domain, curves)


@needs_core
def test_only_the_ports_own_refusal_is_a_refusal():
    import coolplot_core
    from coolplot.engine import plan
    chart = _charts()[0]
    spec = chart.spec
    domain = chart.engine.domain(spec)
    record = native.compose_record(spec, domain, chart.engine.curves(spec, domain, plan(spec, domain)))
    record["spec"]["diagram"] = "xy"
    with pytest.raises(coolplot_core.Error):
        coolplot_core.compose(json.dumps(record))


@needs_core
def test_a_diagram_of_any_axis_pair_composes_the_same_through_the_port(monkeypatch):
    pytest.importorskip("CoolProp")
    from coolplot import DiagramSpec, PropertyDiagram
    from coolplot.core.diagram_type import DiagramType
    chart = PropertyDiagram("R290", DiagramType("T", "h"), tp_limits="ACHP", settings="interactive")
    chart.set_default_lines(labels=True)
    assert chart.spec.to_dict()["diagram"] == "Th"
    assert DiagramSpec.from_dict(chart.spec.to_dict()) == chart.spec
    python, ported = _both_scenes(chart)
    difference = _same(python.to_dict(), ported.to_dict())
    assert difference == "", difference


@needs_core
def test_the_port_composes_the_same_scene():
    for chart in _charts():
        python, ported = _both_scenes(chart)
        assert ported.ids() == python.ids()
        assert ported.axes == python.axes
        difference = _same(python.to_dict(), ported.to_dict())
        assert difference == "", difference


@needs_core
def test_previous_labels_keep_their_items_through_the_port():
    chart = _charts()[0]
    python, _ = _both_scenes(chart)
    from coolplot.engine import plan
    spec = chart.spec
    domain = chart.engine.domain(spec)
    curves = chart.engine.curves(spec, domain, plan(spec, domain))
    cycles = [chart.engine.cycle(spec, c) for c in spec.cycles]
    previous = {item.id: item for item in python if item.role == "isoline_label"}
    items, axes = native.compose(spec, domain, curves, (400.0, 300.0), previous, cycles)
    reference, _ = compose_python(spec, domain, curves, (400.0, 300.0), previous, cycles)
    assert [i.id for i in items] == [i.id for i in reference]
    difference = _same(Scene(axes, items).to_dict(), Scene(axes, reference).to_dict())
    assert difference == "", difference
    # A label that stays where it was comes back as the very same item on both paths
    kept = [i.id for i in reference if previous.get(i.id) is i]
    assert kept and all(items_equal(previous[i.id], i) for i in items if i.id in kept)


@needs_core
def test_the_chart_uses_the_port_and_the_scene_is_the_same(monkeypatch):
    chart = _charts()[0]
    monkeypatch.setenv("COOLPLOT_NATIVE", "1")
    ported = chart.update_scene().to_dict()
    monkeypatch.setenv("COOLPLOT_NATIVE", "0")
    chart.scene.replace_all([])
    python = chart.update_scene().to_dict()
    difference = _same(python, ported)
    assert difference == "", difference


@needs_core
def test_the_svg_writer_of_the_port_is_byte_identical():
    from coolplot.render.svg import SvgRenderer
    scenes = [conformance_scene()]
    for chart in _charts():
        # The chart's own scene (scene order differs from drawing order: the
        # legend follows the scene order) and the same scene through JSON
        scenes.append(chart.update_scene())
        scenes.append(Scene.from_dict(chart.update_scene().to_dict()))
    for scene in scenes:
        python, ported = SvgRenderer(native=False), SvgRenderer(native=True)
        python.sync(scene)
        ported.sync(scene)
        assert ported.to_svg() == python.to_svg()
        assert same_numbers(ported.plot_size_pt(), python.plot_size_pt())


@needs_core
def test_the_svg_backend_on_the_port_passes_the_conformance_kit():
    from coolplot.render.svg import SvgRenderer
    assert run_conformance(lambda: SvgRenderer(native=True)) == []


@needs_core
def test_the_scene_of_the_port_feeds_the_other_renderers():
    pytest.importorskip("matplotlib")
    from coolplot.render.mpl import MatplotlibRenderer
    from coolplot.render.svg import SvgRenderer
    chart = _charts()[0]
    _, ported = _both_scenes(chart)
    for renderer in (MatplotlibRenderer(), SvgRenderer()):
        report = renderer.sync(ported)
        assert sorted(report.added) == sorted(ported.ids())
        for item in ported:
            assert renderer.describe_item(item.id)["visible"] == (item.visible and not (
                item.role in ("isoline_label", "state_number") and not math.isfinite(item.x)))


@needs_core
def test_the_port_reports_its_errors_as_value_errors():
    import coolplot_core
    with pytest.raises(ValueError, match="not valid JSON"):
        coolplot_core.compose("{not json")
    with pytest.raises(ValueError):
        coolplot_core.compose(json.dumps({"spec": {"diagram": "xy"}, "domain": {"ranges_SI": {}}}))
    with pytest.raises(ValueError, match="item type"):
        coolplot_core.scene_to_svg(json.dumps({"items": [{"type": "circle", "id": "c"}]}))


@needs_core
def test_the_pdf_backend_passes_the_conformance_kit():
    from coolplot.render.pdf import PdfRenderer
    assert run_conformance(PdfRenderer) == []


@needs_core
def test_the_pdf_of_a_chart_reads_back(tmp_path):
    from coolplot.render.pdf import PdfRenderer
    from coolplot.testing.pdf_reader import read_pdf
    chart = _charts()[0]
    chart.title = "Propane heat pump"
    renderer = PdfRenderer()
    renderer.sync(chart.update_scene(renderer.plot_size_pt()))
    path = tmp_path / "chart.pdf"
    renderer.save(str(path))
    content = read_pdf(str(path))
    assert content.pages == 1 and content.info["Title"] == "Propane heat pump"
    assert all(not f.problems for f in content.fonts) and content.fonts
    texts = set(content.texts)
    assert "Propane heat pump" in texts and "heat pump" in texts
    assert any(t.startswith("T=") for t in texts)
    with pytest.raises(ValueError, match="PDF"):
        renderer.save(str(tmp_path / "chart.svg"))


@needs_core
def test_the_pdf_page_has_the_svg_geometry_and_all_text_on_it(tmp_path):
    """Margin labels widen the margins and a long legend text is cut, as in SVG."""
    import re
    from dataclasses import replace
    from coolplot.render.pdf import PdfRenderer
    from coolplot.render.svg import SvgRenderer
    from coolplot.testing.pdf_reader import read_pdf
    chart = _charts()[1]   # labels in the margin, outside the frame
    chart.title = "A blend in the margin mode"
    chart.add_cycle("A cycle whose name is far too long to fit into any legend of a page", [
        {"T": 0.0, "Q": 1.0}, {"T": 40.0, "Q": 0.0}])
    renderer = PdfRenderer(margins_pt=(30.0, 5.0, 10.0, 30.0))
    scene = chart.update_scene(renderer.plot_size_pt())
    for location in ("outside right", "upper left"):
        style = scene.axes.style
        scene.set_axes(replace(scene.axes, style=replace(style, legend=replace(style.legend, location=location))))
        renderer.sync(scene)
        assert renderer.plot_size_pt() == pytest.approx(SvgRenderer.plot_size_pt(renderer), abs=1e-6)
        # The margin labels make the margins larger than the ones given, so
        # the check above is not vacuous
        base_w, base_h = 576.0 - 30.0 - 5.0, 432.0 - 10.0 - 30.0
        assert renderer.plot_size_pt()[0] < base_w - 1.0 or renderer.plot_size_pt()[1] < base_h - 1.0
        data = native.scene_to_pdf(renderer._axes, renderer._scene_items(), renderer.width_pt, renderer.height_pt,
                                   renderer.margins_pt, compress=False)
        size = None
        found = 0
        for token in re.finditer(rb"/F\d+ (\S+) Tf|(\S+) (\S+) \S+ \S+ (\S+) (\S+) Tm <([0-9A-F]*)> Tj", data):
            if token.group(1):
                size = float(token.group(1))
                continue
            c, s, x, y = (float(token.group(k)) for k in (2, 3, 4, 5))
            glyphs = len(token.group(6)) // 4
            assert 0.0 <= x <= renderer.width_pt and 0.0 <= y <= renderer.height_pt, token.group(0)[:80]
            # The far end, with glyphs at least 0.4 em wide, stays on the page too
            end_x, end_y = x + c * 0.4 * size * glyphs, y + s * 0.4 * size * glyphs
            assert -1.0 <= end_x <= renderer.width_pt + 1.0 and -1.0 <= end_y <= renderer.height_pt + 1.0
            found += 1
        assert found > 20
        path = tmp_path / "page.pdf"
        path.write_bytes(data)
        texts = read_pdf(str(path)).texts
        assert any(t.startswith("A cycle whose") and t.endswith("...") for t in texts), texts
