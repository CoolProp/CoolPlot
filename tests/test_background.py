# -*- coding: utf-8 -*-
"""Background calculation: never waiting, coarse then fine, cancelling."""
import pickle
import threading

import numpy as np
import pytest

pytest.importorskip("CoolProp")

from coolplot import PropertyDiagram  # noqa: E402
from coolplot.engine import BackgroundEngine  # noqa: E402
from coolplot.engine.plan import plan  # noqa: E402
from coolplot.thermo.isolines import Curve  # noqa: E402


def _diagram(**kwargs):
    d = PropertyDiagram("HEOS::R290", "ph", tp_limits="ACHP", **kwargs)
    d.set_isolines("Q", num=3)
    d.set_isolines("T", values=[-20.0, 0.0, 20.0], points=80)
    return d


def _settle(d):
    """Let all background work finish and take the final scene."""
    for _ in range(5):
        d.update_scene()
        if not d.engine.busy:
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
        d.set_isolines("T", values=[50.0, 60.0], points=80)
        d.update_scene()
        second = set(d.engine._jobs)
        # The queued work for the old isotherms is gone, the new one queued
        assert not any(k[3] in (253.15, 293.15) and k[2] == "T" for k in second)
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
