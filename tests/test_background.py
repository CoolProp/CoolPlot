# -*- coding: utf-8 -*-
"""Background calculation: never waiting, coarse then fine, cancelling."""
import pickle
from dataclasses import replace
import threading

import numpy as np
import pytest

pytest.importorskip("CoolProp")

from coolplot import PropertyDiagram  # noqa: E402
from coolplot.core.floats import same_number  # noqa: E402
from coolplot.engine import BackgroundEngine  # noqa: E402
from coolplot.engine.planning import plan  # noqa: E402
from coolplot.render.svg import SvgRenderer  # noqa: E402
from coolplot.thermo.isolines import Curve  # noqa: E402


def _diagram(**kwargs):
    d = PropertyDiagram("HEOS::R290", "ph", tp_limits="ACHP", **kwargs)
    d.set_lines("Q", num=3)
    d.set_lines("T", values=[-20.0, 0.0, 20.0], points=80)
    return d


def _settle(d):
    """Let all background work finish and take the final scene."""
    for _ in range(5):
        d.update_scene()
        if not d.engine.busy and d.progress[0] >= d.progress[1]:
            break
        assert d.wait(60.0)
    return d.update_scene()


@pytest.mark.parametrize("mode", ["threads", "processes"])
def test_background_gives_the_same_scene(mode):
    reference = _diagram().update_scene()
    d = _diagram(background=mode)
    try:
        scene = _settle(d)
        assert sorted(scene.ids()) == sorted(reference.ids())
        for item in reference:
            np.testing.assert_allclose(scene[item.id].x, item.x, equal_nan=True)
        assert d.progress == (6, 6)
    finally:
        d.close()


def test_the_first_scene_does_not_wait():
    d = _diagram(background="threads", settings=None)
    gate = threading.Event()
    # Block the only worker, so nothing can be computed yet
    d.engine._pool.submit(gate.wait)
    try:
        scene = d.update_scene()
        assert len([i for i in scene if i.group.startswith("iso/")]) == 0
        assert d.progress == (0, 6) and d.engine.busy
    finally:
        gate.set()
        _settle(d)
        d.close()


def test_previews_are_drawn_until_the_final_curve_arrives():
    d = _diagram(background="threads")
    engine = d.engine
    spec = d.spec
    domain = engine.domain(spec)
    gate = threading.Event()
    engine._pool.submit(gate.wait)
    try:
        # Put a preview in place by hand; the final curve cannot be computed yet
        request = next(r for r in plan(spec, domain) if r.key == "T")
        preview = Curve([1e5, 2e5], [1e5, 2e5])
        from dataclasses import replace
        engine.cache.put(engine.cache_key(spec, domain, replace(request, points=spec.settings.calc.preview_points)),
                         preview)
        scene = d.update_scene()
        assert scene[request.item_id].x.tolist() == pytest.approx([100.0, 200.0])   # kJ/kg
    finally:
        gate.set()
    final = _settle(d)
    assert len(final[request.item_id].x) > 2
    d.close()


def test_outdated_work_is_cancelled():
    d = _diagram(background="threads", settings="screen")
    gate = threading.Event()
    d.engine._pool.submit(gate.wait)
    try:
        d.update_scene()
        first = set(d.engine._jobs)
        d.set_lines("T", values=[50.0, 60.0], points=80)
        d.update_scene()
        second = set(d.engine._jobs)
        # The queued work for the old isotherms is gone, the new one queued
        # A cache key is (fluid, fingerprint, diagram, key, value_SI, ...)
        assert not any(k[3] == "T" and any(same_number(k[4], v) for v in (253.15, 293.15)) for k in second)
        assert first - second
    finally:
        gate.set()
        _settle(d)
        d.close()


def test_on_ready_is_called_once_per_update():
    calls = []
    done = threading.Event()

    def on_ready(diagram):
        calls.append(diagram)
        done.set()

    d = _diagram(background="threads", on_ready=on_ready)
    try:
        d.update_scene()
        assert done.wait(60.0)
        d.wait(60.0)
        assert len(calls) == 1 and calls[0] is d   # no flood before the next update
    finally:
        d.close()


def test_draw_waits_for_the_complete_picture():
    from coolplot.render.svg import SvgRenderer
    d = _diagram(background="threads")
    try:
        d.draw(SvgRenderer())
        assert d.progress == (6, 6)
        assert len(d.scene["iso/T/273.15"].x) > 40
    finally:
        d.close()


def test_curves_survive_pickling_read_only():
    c = pickle.loads(pickle.dumps(Curve([1.0, 2.0], [3.0, 4.0], 1, method="tracer")))
    assert not c.x.flags.writeable and c.n_failed == 1 and c.method == "tracer"


def test_bad_modes():
    with pytest.raises(ValueError):
        BackgroundEngine("fibres")


def test_close_cancels_and_releases_waiters():
    d = _diagram(background="threads")
    gate = threading.Event()
    d.engine._pool.submit(gate.wait)   # keep the work queued
    d.update_scene()
    assert d.engine.busy
    d.close()
    gate.set()
    assert d.wait(10.0) and not d.engine.busy
    with pytest.raises(RuntimeError):
        d.update_scene()


def test_failures_are_retried_then_reported(monkeypatch):
    import coolplot.engine.background as background
    calls = {"n": 0}
    real = background.compute_curve

    def flaky(*args):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RuntimeError("worker hiccup")
        return real(*args)

    monkeypatch.setattr(background, "compute_curve", flaky)
    d = PropertyDiagram("HEOS::R290", "ph", tp_limits="ACHP", background="threads",
                        settings=None)
    d.set_lines("T", values=[0.0], points=40)
    d.spec = d.spec.with_(settings=d.spec.settings.with_(calc=replace(d.spec.settings.calc, preview_points=0)))
    try:
        # The first attempt fails, the next request tries again; after the
        # second failure the line is given up with a warning naming the error
        d.update_scene()
        d.wait(30.0)
        d.update_scene()
        d.wait(30.0)
        with pytest.warns(UserWarning, match="worker hiccup"):
            scene = d.update_scene()
        assert [i for i in scene if i.group.startswith("iso/T")] == []
        assert d.progress == (1, 1) and not d.engine.busy
    finally:
        d.close()

    # A single failure is retried and the line arrives
    calls["n"] = 1
    d = PropertyDiagram("HEOS::R290", "ph", tp_limits="ACHP", background="threads")
    d.set_lines("T", values=[0.0], points=40)
    d.spec = d.spec.with_(settings=d.spec.settings.with_(calc=replace(d.spec.settings.calc, preview_points=0)))
    try:
        scene = _settle(d)
        assert len([i for i in scene if i.group.startswith("iso/T")]) == 1
    finally:
        d.close()


def test_a_background_engine_serves_one_diagram():
    a = _diagram(background="threads")
    try:
        with pytest.raises(ValueError, match="share the cache"):
            PropertyDiagram("HEOS::R290", "ph", engine=a.engine)
        b = PropertyDiagram("HEOS::R290", "ph", tp_limits="ACHP", background="threads", cache=a.cache)
        b.close()
    finally:
        a.close()


def test_on_ready_never_runs_in_the_asking_thread():
    from concurrent.futures import Future

    class DonePool:
        """A pool whose work is done before the callback is attached."""
        def submit(self, fn, *args):
            future = Future()
            future.set_result(fn(*args))
            return future

        def shutdown(self, **kwargs):
            pass

    calls = []
    done = threading.Event()

    def on_ready(engine):
        calls.append((threading.current_thread() is threading.main_thread(), engine._lock._is_owned()))
        done.set()

    engine = BackgroundEngine("threads", on_ready=on_ready)
    engine._pool = DonePool()
    d = _diagram(engine=engine)
    d.update_scene()
    assert done.wait(10.0)
    assert calls[0] == (False, False)


def _crash_at_zero(fluid, diagram, key, value_SI, *args):
    """compute_curve that kills its worker process for the 0 deg C isotherm."""
    import os
    from coolplot.engine import background
    if key == "T" and abs(value_SI - 273.15) < 1e-6:
        os._exit(1)
    return background._real_compute_curve(fluid, diagram, key, value_SI, *args)


def test_a_crashing_line_costs_only_itself(monkeypatch):
    import multiprocessing
    import warnings
    from coolplot.engine import background
    if multiprocessing.get_start_method() != "fork":
        pytest.skip("the patched worker function only reaches forked workers")
    monkeypatch.setattr(background, "_real_compute_curve", background.compute_curve, raising=False)
    monkeypatch.setattr(background, "compute_curve", _crash_at_zero)
    from concurrent.futures.process import _ExecutorManagerThread
    before = set(threading.enumerate())
    d = PropertyDiagram("HEOS::R290", "ph", tp_limits="ACHP", background="processes", workers=2)
    d.set_lines("T", values=[-20.0, 0.0, 20.0, 40.0, 60.0], points=40)
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            d.draw(SvgRenderer())
        skipped = [str(w.message) for w in caught if "Skipping the line" in str(w.message)]
        assert len(skipped) == 1 and "T=273.15" in skipped[0]
        assert len([i for i in d.scene if i.group == "iso/T"]) == 4
    finally:
        d.close()
    # The pools wind down after close(), also the one whose worker crashed:
    # their manager threads are not daemons, a stuck one keeps Python from exiting
    managers = [t for t in threading.enumerate() if isinstance(t, _ExecutorManagerThread) and t not in before]
    for t in managers:
        t.join(20.0)
    assert not [t for t in managers if t.is_alive()]


def test_no_notification_after_close():
    calls = []
    d = _diagram(background="threads", on_ready=lambda diagram: calls.append(diagram))
    gate = threading.Event()
    d.engine._pool.submit(gate.wait)
    d.update_scene()
    d.close()
    gate.set()
    d.wait(10.0)
    assert calls == []


def test_the_engine_is_free_again_after_its_diagram_is_gone():
    import gc
    engine = BackgroundEngine("threads")
    first = PropertyDiagram("HEOS::R290", "ph", engine=engine)
    del first
    gc.collect()
    PropertyDiagram("HEOS::R290", "ph", engine=engine)   # no error
    engine.close()


def test_a_diagram_with_on_ready_is_freed_when_dropped():
    import gc
    d = PropertyDiagram("HEOS::R290", "ph", background="threads", on_ready=lambda diagram: None)
    engine = d.engine
    del d
    gc.collect()
    # The finalizer of the diagram ran: its callback did not keep it alive
    assert engine.claimed is False
    engine.close()


def test_a_shared_cache_survives_threads_that_fill_it():
    import sys
    import time
    from coolplot.engine import CurveCache
    cache = CurveCache(max_size=4)   # tiny: almost every store drops another curve
    errors = []
    stop = threading.Event()

    def writer():
        i = 0
        try:
            while not stop.is_set():
                cache.put(i % 5, i)
                i += 1
        except Exception as error:
            errors.append(error)

    def reader():
        try:
            while not stop.is_set():
                for key in range(5):
                    cache.peek(key)
                    cache.get_or_compute(key, lambda: 0)
        except Exception as error:
            errors.append(error)

    interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)   # switch threads as often as possible
    try:
        threads = [threading.Thread(target=f) for f in (writer, writer, reader, reader)]
        for t in threads:
            t.start()
        time.sleep(1.0)
        stop.set()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(interval)
    assert errors == []
