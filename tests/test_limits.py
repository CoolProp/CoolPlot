# -*- coding: utf-8 -*-
"""TpLimits.around: a calculation region that follows the states of cycles."""
import numpy as np
import pytest

from coolplot import Cycle, StatePoint, TpLimits

STATES = [StatePoint(T=268.15, p=4.0e5), StatePoint(T=343.15, p=16.0e5), StatePoint(T=318.15, p=16.0e5)]


def _bounds(limits):
    return (limits.T_min, limits.T_max, limits.p_min, limits.p_max)


def test_around_states():
    assert _bounds(TpLimits.around(STATES)) == pytest.approx((228.15, 383.15, 2.0e5, 32.0e5))


def test_around_a_cycle():
    cycle = Cycle("hp", states=dict(enumerate(STATES, start=1)))
    assert TpLimits.around(cycle) == TpLimits.around(STATES)


def test_around_several_cycles_and_states():
    first = Cycle("a", states={1: STATES[0], 2: STATES[1]})
    second = Cycle("b", states={1: STATES[2]})
    extra = StatePoint(T=400.0, p=50e5)
    limits = TpLimits.around(first, second, extra)
    assert _bounds(limits) == pytest.approx((228.15, 440.0, 2.0e5, 100e5))


def test_around_plain_dicts():
    assert TpLimits.around([{"T": 268.15, "p": 4e5}, {"T": 343.15, "p": 16e5}]) == TpLimits.around(STATES[:2])


def test_around_with_own_margins():
    limits = TpLimits.around(STATES, T_margin_K=10.0, p_factor=1.5)
    assert _bounds(limits) == pytest.approx((258.15, 353.15, 4.0e5 / 1.5, 24.0e5))


def test_around_without_states_raises():
    with pytest.raises(ValueError, match="state"):
        TpLimits.around([])


def test_around_needs_temperature_and_pressure():
    with pytest.raises(ValueError, match="'p'"):
        TpLimits.around([StatePoint(T=300.0, h=4e5)])


@pytest.mark.parametrize("kwargs, match", [
    ({"T_margin_K": -1.0}, "T_margin_K"),
    ({"p_factor": 0.5}, "p_factor"),
])
def test_around_rejects_margins_that_shrink_the_region(kwargs, match):
    with pytest.raises(ValueError, match=match):
        TpLimits.around(STATES, **kwargs)


def test_isotherms_follow_the_cycle():
    """With the default region, which reaches down to the triple point, the
    isotherms of R290 are few and stop inside the dome; around the cycle
    they come in steps of 10 K and run through the liquid."""
    pytest.importorskip("CoolProp")
    from coolplot import PropertyDiagram
    from coolplot.thermo.cycles import simple_compression

    cycle = simple_compression("R290", T_evap_C=0, T_cond_C=50, dT_sh_K=5)
    diagram = PropertyDiagram("R290", "ph", units="engineering", tp_limits=TpLimits.around(cycle))
    diagram.set_default_lines(rounding=True)
    diagram.add_cycle(cycle)
    scene = diagram.update_scene()
    values = sorted(float(i.split("/")[2]) for i in scene.ids()
                    if i.startswith("iso/T/") and not i.endswith("/label"))
    assert max(np.diff(values)) <= 10.0 + 1e-9
    # the 0 deg C isotherm continues from the dome into the liquid
    freezing = scene["iso/T/273.15"]
    p_sat_bar = diagram.state({"T": 0, "Q": 0})["p"] / 1e5
    assert np.nanmax(freezing.y) > 2 * p_sat_bar
