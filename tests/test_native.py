# -*- coding: utf-8 -*-
"""The lines CoolProp's C++ port of the numerics computes (CoolProp.Plot).

The tests marked ``needs_port`` run only with a CoolProp that carries the
port; the released wheels up to 8.0.0 do not, and then they are skipped
(in CI too). They mirror the checks of test_numerics.py on the Python
reference and compare the two. The tests of the provider's choice, the
switch and the fluid strings run everywhere, with a stand-in for the port.
"""
import numpy as np
import pytest

CoolProp = pytest.importorskip("CoolProp")
from CoolProp.CoolProp import PropsSI  # noqa: E402

from coolplot.thermo import DiagramType, Fluid, compute_isoline, get_tp_limits, resolve_tp_box  # noqa: E402
from coolplot.thermo import native  # noqa: E402
from coolplot.thermo.isolines import Curve  # noqa: E402
from coolplot.thermo.provider import compute_curve  # noqa: E402

needs_port = pytest.mark.skipif(not native.available(), reason="this CoolProp has no CoolProp.CoolProp.Plot")

TS = DiagramType.parse("Ts")
PH = DiagramType.parse("ph")


@pytest.fixture(scope="module")
def r290():
    return Fluid("HEOS::R290")


@pytest.fixture(scope="module")
def blend():
    return Fluid("HEOS::R32[0.7]&R125[0.3]")


def _native(fluid, diagram, key, value, points=50, solver="auto"):
    box = resolve_tp_box(fluid, get_tp_limits("ACHP"))
    curve = native.compute_curve(fluid, diagram, key, value, box, points, solver, 1e-7, "critical")
    assert curve is not None
    return curve


def test_fluid_strings_name_the_model():
    assert native.fluid_string(Fluid("HEOS::R290").model_key) == "HEOS::R290"
    assert native.fluid_string(Fluid("HEOS::R32[0.7]&R125[0.3]").model_key) == "HEOS::R32[0.7]&R125[0.3]"
    assert native.fluid_string(Fluid("INCOMP::MEG[0.5]").model_key) == "INCOMP::MEG[0.5]"
    # A mixture given as an AbstractState or as a predefined blend carries
    # CoolProp's own interaction parameters, which count as unchanged
    state = CoolProp.AbstractState("HEOS", "R32&R125")
    state.set_mole_fractions([0.7, 0.3])
    assert native.fluid_string(Fluid(state).model_key) == "HelmholtzEOSMixtureBackend::R32[0.7]&R125[0.3]"
    mix = native.fluid_string(Fluid("HEOS::R407C.mix").model_key)
    assert mix is not None and "::R32[" in mix and "&R125[" in mix and "&R134a[" in mix
    # A model the string cannot carry goes to the Python numerics
    model = Fluid(state).model_key
    changed = tuple((i, j, k, v + 0.1) for i, j, k, v in model[4][:1]) + model[4][1:]
    assert native.fluid_string(model[:4] + (changed,)) is None
    assert native.fluid_string(("HEOS", ("R32", "R125"), (0.7, 0.3), "mass", ())) is None


def test_quality_lines_of_a_tabular_backend_use_its_equation_of_state():
    try:
        tabular = Fluid("BICUBIC&HEOS::R290")
    except Exception:
        pytest.skip("tabular backends are not available")
    assert native.port_fluid_string(tabular, "T") == "BICUBIC&HEOS::R290"
    assert native.port_fluid_string(tabular, "Q") == "HEOS::R290"


def test_the_switch(monkeypatch):
    monkeypatch.setenv("COOLPLOT_NATIVE", "0")
    assert not native.enabled()
    monkeypatch.setenv("COOLPLOT_NATIVE", "1")
    assert native.enabled() == native.available()


def test_each_thread_gets_its_own_plot(monkeypatch):
    """A PropertyPlot computes with one CoolProp state and the port releases
    the interpreter lock, so threads must not share one."""
    import threading
    from types import SimpleNamespace

    class StandInPlot:
        def __init__(self, *args):
            self.args = args

    monkeypatch.setattr(native, "_Plot", SimpleNamespace(PropertyPlot=StandInPlot))
    monkeypatch.setattr(native, "_KEYS", {"p": 1, "h": 2})
    monkeypatch.setattr(native, "_LOCAL", threading.local())
    diagram = SimpleNamespace(x="h", y="p")
    box = (200.0, 300.0, 1e5, 1e6)
    mine = native._plot("R290", None, diagram, box)
    assert native._plot("R290", None, diagram, box) is mine     # kept for the lines of one chart
    other = []
    worker = threading.Thread(target=lambda: other.append(native._plot("R290", None, diagram, box)))
    worker.start()
    worker.join()
    assert other[0] is not mine


def test_the_provider_asks_the_port_first(r290, monkeypatch):
    """With a stand-in for the port: the provider returns what the port
    computes, leaves it alone when the switch is off, and falls back to the
    Python numerics when the port declines a line."""
    box = resolve_tp_box(r290, get_tp_limits("ACHP"))
    sentinel = Curve([1.0, 2.0], [3.0, 4.0], method="port")
    calls = []

    def stand_in(*args):
        calls.append(args)
        return sentinel
    monkeypatch.setattr(native, "available", lambda: True)
    monkeypatch.setattr(native, "compute_curve", stand_in)
    monkeypatch.setenv("COOLPLOT_NATIVE", "1")
    assert compute_curve(r290, TS, "p", 5e5, box, 20, "auto", 1e-7, "critical") is sentinel
    assert len(calls) == 1 and calls[0][2] == "p" and calls[0][5] == 20
    monkeypatch.setenv("COOLPLOT_NATIVE", "0")
    python = compute_curve(r290, TS, "p", 5e5, box, 20, "auto", 1e-7, "critical")
    assert len(calls) == 1 and python.method == "flash" and python.n_inserted == 2
    monkeypatch.setenv("COOLPLOT_NATIVE", "1")
    monkeypatch.setattr(native, "compute_curve", lambda *args: None)
    assert compute_curve(r290, TS, "p", 5e5, box, 20, "auto", 1e-7, "critical").n_inserted == 2


@needs_port
def test_isobar_runs_horizontally_through_the_dome(r290):
    p_Pa = 5e5
    curve = _native(r290, TS, "p", p_Pa)
    assert curve.n_inserted == 2 and curve.n_failed == 0 and curve.method == "flash"
    T_sat_K = PropsSI("T", "P", p_Pa, "Q", 0, "R290")
    s_liq, s_vap = (PropsSI("S", "P", p_Pa, "Q", q, "R290") for q in (0, 1))
    i = int(np.argmin(np.abs(curve.x - s_liq)))
    j = int(np.argmin(np.abs(curve.x - s_vap)))
    assert curve.x[i] == pytest.approx(s_liq, rel=1e-9) and curve.x[j] == pytest.approx(s_vap, rel=1e-9)
    assert j > i + 1 and curve.y[i:j + 1] == pytest.approx(T_sat_K, rel=1e-9)
    assert np.all(np.diff(curve.y) >= -1e-9) and np.all(np.diff(curve.x) > 0.0)


@needs_port
def test_isotherm_in_ph_has_its_kinks_on_the_dome(r290):
    curve = _native(r290, PH, "T", 280.0, points=30)
    assert curve.n_inserted == 2
    for q in (0, 1):
        h = PropsSI("H", "T", 280.0, "Q", q, "R290")
        assert np.min(np.abs(curve.x - h)) < 1e-6 * h


@needs_port
def test_isenthalp_meets_the_bubble_line_exactly(r290):
    curve = _native(r290, TS, "h", 3e5, points=40)
    assert curve.n_inserted >= 1
    inside = (170.0 < curve.y) & (curve.y < 369.0)
    s_liq = np.array([PropsSI("S", "T", T, "Q", 0, "R290") for T in curve.y[inside]])
    assert np.min(np.abs(curve.x[inside] - s_liq)) < 1e-6 * np.max(s_liq)


@needs_port
def test_auto_solver_traces_mixtures_only(r290, blend):
    assert _native(r290, TS, "p", 5e5, points=10).method == "flash"
    assert _native(blend, TS, "p", 5e5, points=10).method == "tracer"
    with pytest.raises(ValueError):
        _native(blend, TS, "p", 5e5, points=10, solver="newton")


@needs_port
def test_mixture_dome_from_the_phase_envelope(blend):
    box = resolve_tp_box(blend, get_tp_limits("ACHP"))
    bubble = native.compute_curve(blend, PH, "Q", 0.0, box, 50, "auto", 1e-7, "critical")
    dew = native.compute_curve(blend, PH, "Q", 1.0, box, 50, "auto", 1e-7, "critical")
    assert bubble.method == dew.method == "envelope"
    assert bubble.n_failed == 0 and dew.n_failed == 0
    assert (bubble.x[0], bubble.y[0]) == (dew.x[-1], dew.y[-1])
    state = CoolProp.AbstractState("HEOS", "R32&R125")
    state.set_mole_fractions([0.7, 0.3])
    state.build_phase_envelope("veryfine")
    data = state.get_phase_envelope_data()
    on_bubble = np.array(data.Q) == 0.0
    assert bubble.y[1:] == pytest.approx(np.array(data.p)[on_bubble], rel=1e-12)


@needs_port
def test_blend_lines_meet_the_dome_near_the_critical_point(blend):
    isochore = _native(blend, PH, "rho", 300.0, points=40)
    assert isochore.n_inserted == 1
    isotherm = _native(blend, PH, "T", 340.0, points=40)
    assert isotherm.n_inserted == 2


@needs_port
def test_pure_quality_lines_end_at_the_critical_point(r290):
    box = resolve_tp_box(r290, get_tp_limits("DEF"))
    for quality in (0.0, 0.5, 1.0):
        curve = native.compute_curve(r290, PH, "Q", quality, box, 40, "auto", 1e-7, "critical")
        assert curve.n_failed == 0 and len(curve.x) == 41
        assert curve.y[-1] == pytest.approx(r290.critical["p"], rel=1e-9)
        assert curve.x[-1] == pytest.approx(r290.critical["h"], rel=1e-9)


@needs_port
@pytest.mark.parametrize("fluid_name, key, value, diagram", [
    ("r290", "p", 5e5, TS), ("r290", "T", 280.0, PH), ("r290", "h", 3e5, TS), ("r290", "s", 1500.0, PH),
    ("r290", "rho", 300.0, PH), ("r290", "Q", 0.5, PH),
    ("blend", "p", 5e5, TS), ("blend", "T", 280.0, PH), ("blend", "h", 3e5, TS), ("blend", "rho", 300.0, PH),
    ("blend", "Q", 0.5, PH)])
def test_the_port_agrees_with_the_python_reference(request, fluid_name, key, value, diagram):
    """The port steps exactly as the Python numerics do: the same points,
    the same gaps, the same diagnostics, to the rounding of the solvers."""
    fluid = request.getfixturevalue(fluid_name)
    box = resolve_tp_box(fluid, get_tp_limits("ACHP"))
    python = compute_isoline(fluid, diagram, key, value, box, points=40)
    port = native.compute_curve(fluid, diagram, key, value, box, 40, "auto", 1e-7, "critical")
    assert (port.n_inserted, port.method, port.n_failed) == (python.n_inserted, python.method, python.n_failed)
    assert len(port.x) == len(python.x) >= 10
    assert np.array_equal(np.isnan(port.x), np.isnan(python.x))
    finite = np.isfinite(python.x)
    assert port.x[finite] == pytest.approx(python.x[finite], rel=1e-9)
    assert port.y[finite] == pytest.approx(python.y[finite], rel=1e-9)


@needs_port
def test_the_provider_uses_the_port_when_enabled(r290, monkeypatch):
    box = resolve_tp_box(r290, get_tp_limits("ACHP"))
    monkeypatch.setenv("COOLPLOT_NATIVE", "1")
    port = compute_curve(r290, TS, "p", 5e5, box, 20, "auto", 1e-7, "critical")
    monkeypatch.setenv("COOLPLOT_NATIVE", "0")
    python = compute_curve(r290, TS, "p", 5e5, box, 20, "auto", 1e-7, "critical")
    assert port.x == pytest.approx(python.x, rel=1e-9, nan_ok=True)
    assert port.n_inserted == python.n_inserted == 2


def test_the_flag_of_the_cache_key_decides_not_the_mode_at_compute_time(monkeypatch, r290):
    """A worker process does not see set_native_mode of its parent, and the mode
    may change while jobs are queued: the curve is computed the way its key says."""
    from coolplot import PropertyDiagram, set_native_mode
    from coolplot.engine import Engine, plan
    box = resolve_tp_box(r290, get_tp_limits("ACHP"))
    sentinel = Curve([1.0, 2.0], [3.0, 4.0], method="port")
    monkeypatch.setattr(native, "available", lambda: True)
    monkeypatch.setattr(native, "compute_curve", lambda *args: sentinel)
    set_native_mode("on")
    assert compute_curve(r290, TS, "p", 5e5, box, 20, "auto", 1e-7, "critical", use_native=False) is not sentinel
    set_native_mode("off")
    assert compute_curve(r290, TS, "p", 5e5, box, 20, "auto", 1e-7, "critical", use_native=True) is sentinel
    # The engine hands the flag of the key to the computation
    chart = PropertyDiagram("R290", "Ts", tp_limits="ACHP", settings="interactive")
    chart.set_lines("p", values=[5.0])
    spec = chart.spec
    engine = Engine()
    domain = engine.domain(spec)
    request = [r for r in plan(spec, domain) if r.key == "p"][0]
    set_native_mode("on")
    key = engine.cache_key(spec, domain, request)
    assert Engine.key_uses_native(key)
    seen = []
    import coolplot.engine.engine as engine_module
    real = engine_module.compute_curve
    monkeypatch.setattr(engine_module, "compute_curve", lambda *a, **k: seen.append(k) or real(*a, **k))
    assert engine.curve(spec, domain, request) is sentinel and seen[-1]["use_native"] is True
    set_native_mode("off")
    assert not Engine.key_uses_native(engine.cache_key(spec, domain, request))
    assert engine.curve(spec, domain, request) is not sentinel and seen[-1]["use_native"] is False
