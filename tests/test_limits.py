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
    limits = TpLimits.around(STATES, dT_margin_K=10.0, p_factor=1.5)
    assert _bounds(limits) == pytest.approx((258.15, 353.15, 4.0e5 / 1.5, 24.0e5))


def test_around_without_states_raises():
    with pytest.raises(ValueError, match="state"):
        TpLimits.around([])


def test_around_needs_temperature_and_pressure():
    with pytest.raises(ValueError, match="'p'"):
        TpLimits.around([StatePoint(T=300.0, h=4e5)])


@pytest.mark.parametrize("kwargs, match", [
    ({"dT_margin_K": -1.0}, "dT_margin_K"),
    ({"p_factor": 0.5}, "p_factor"),
])
def test_around_rejects_margins_that_shrink_the_region(kwargs, match):
    with pytest.raises(ValueError, match=match):
        TpLimits.around(STATES, **kwargs)


def test_around_a_named_collection_of_states():
    limits = TpLimits.around({"evaporator": STATES[0], "condenser": STATES[1]})
    assert _bounds(limits) == pytest.approx((228.15, 383.15, 2.0e5, 32.0e5))


def test_around_a_named_collection_of_cycles():
    cycle = Cycle("hp", states=dict(enumerate(STATES, start=1)))
    assert TpLimits.around({"hp": cycle}) == TpLimits.around(STATES)


def test_around_an_incomplete_state_dict_names_the_missing_quantity():
    with pytest.raises(ValueError, match="'p'"):
        TpLimits.around({"T": 300.0, "h": 4e5})
    with pytest.raises(ValueError, match="'T'"):
        TpLimits.around([{"p": 4e5}])


def test_around_an_empty_collection_raises():
    with pytest.raises(ValueError, match="at least one state"):
        TpLimits.around({})


def test_around_accepts_the_aliases_of_quantities():
    assert TpLimits.around([{"t": 268.15, "P": 4e5}, {"T": 343.15, "p": 16e5}]) == TpLimits.around(STATES[:2])


@pytest.mark.parametrize("order", [1, -1])
def test_around_rejects_a_state_that_is_not_a_number(order):
    states = [StatePoint(T=float("nan"), p=4e5), STATES[0]][::order]
    with pytest.raises(ValueError, match="finite"):
        TpLimits.around(states)


def test_around_rejects_values_that_cannot_be_SI():
    """States in chart units (deg C, bar) would give a region near 0 K."""
    with pytest.raises(ValueError, match="K and"):
        TpLimits.around([{"T": -5.0, "p": 4.0}, {"T": 70.0, "p": 16.0}])


def test_around_rejects_values_that_are_not_numbers():
    with pytest.raises(ValueError, match="'T'"):
        TpLimits.around([{"T": None, "p": 4e5}])


def test_around_rejects_an_empty_region():
    with pytest.raises(ValueError, match="Empty"):
        TpLimits.around([STATES[0]], dT_margin_K=0.0, p_factor=1.0)


def test_around_rejects_other_sources():
    with pytest.raises(TypeError, match="cycles, states"):
        TpLimits.around(STATES, 10.0)


def test_around_the_states_of_a_chart():
    pytest.importorskip("CoolProp")
    from coolplot import PropertyDiagram
    from coolplot.thermo.cycles import simple_compression

    cycle = simple_compression("R290", T_evap_C=-10, T_cond_C=50, dT_sh_K=5)
    diagram = PropertyDiagram("R290", "ph", units="engineering")
    diagram.add_cycle(cycle)
    states = diagram.cycle_states(cycle.name)
    assert TpLimits.around(states) == TpLimits.around(states.values()) == TpLimits.around(cycle)
    diagram.tp_limits = TpLimits.around(states)
    assert diagram.tp_limits == TpLimits.around(cycle)
    # states converted to the chart's units are not SI; a temperature below 0 deg C gives it away
    with pytest.raises(ValueError, match="K and"):
        TpLimits.around(diagram.cycle_states(cycle.name, units="engineering"))


def test_isotherms_follow_the_cycle():
    """With the default region, which reaches down to the triple point, the
    isotherms of R290 are few and stop inside the dome; around the cycle
    they come in steps of 10 K and run through the liquid."""
    pytest.importorskip("CoolProp")
    from coolplot import PropertyDiagram
    from coolplot.thermo.cycles import simple_compression

    cycle = simple_compression("R290", T_evap_C=0, T_cond_C=50, dT_sh_K=5)

    def isotherms(limits):
        diagram = PropertyDiagram("R290", "ph", units="engineering", tp_limits=limits)
        diagram.set_default_lines(rounding=True)
        diagram.add_cycle(cycle)
        scene = diagram.update_scene()
        values = sorted(float(i.split("/")[2]) for i in scene.ids()
                        if i.startswith("iso/T/") and not i.endswith("/label"))
        p_sat_bar = diagram.state({"T": 0, "Q": 0})["p"] / 1e5
        return values, np.nanmax(scene["iso/T/273.15"].y) / p_sat_bar

    values, reach = isotherms(TpLimits.around(cycle))
    assert max(np.diff(values)) <= 10.0 + 1e-9
    assert reach > 2   # the 0 deg C isotherm continues from the dome into the liquid
    default_values, default_reach = isotherms("DEF")
    assert min(np.diff(default_values)) >= 50.0 - 1e-9
    assert default_reach == pytest.approx(1.0, abs=1e-3)
