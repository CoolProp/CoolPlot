# -*- coding: utf-8 -*-
"""Labels inside the dome, next to the bubble and dew lines (LabelSettings.dome, 1.6)."""
import json
import math

import pytest

pytest.importorskip("CoolProp")

from coolplot import DiagramSpec, PropertyDiagram  # noqa: E402
from coolplot.compose.builder import default_plot_size_pt  # noqa: E402
from coolplot.compose.layout import DOME_GAP_PT, Frame, text_size_pt  # noqa: E402
from coolplot.spec.diagram import dome_key  # noqa: E402


def _dome(diagram):
    return {item.id: item for item in diagram.update_scene() if "/dome/" in item.id}


def _chart(fluid="R290", diagram_type="ph", family="T", **labels):
    diagram = PropertyDiagram(fluid, diagram_type, units="engineering", tp_limits="ACHP")
    diagram.set_lines(family, num=8, rounding=True, labels=True)
    diagram.settings = diagram.settings.with_(labels=dict({"dome": True}, **labels))
    return diagram


def test_off_by_default_and_kept_out_of_the_record():
    diagram = PropertyDiagram("R290", "ph", tp_limits="ACHP")
    diagram.set_lines("T", num=8, labels=True)
    assert diagram.settings.labels.dome is False
    assert _dome(diagram) == {}
    assert "dome" not in diagram.spec.to_dict()["settings"]["labels"]


def test_the_setting_survives_json():
    diagram = _chart()
    record = json.loads(json.dumps(diagram.spec.to_dict()))
    assert record["settings"]["labels"]["dome"] is True
    assert DiagramSpec.from_dict(record) == diagram.spec


@pytest.mark.parametrize("diagram_type, key", [("ph", "T"), ("hs", "T"), ("ps", "T"), ("Ts", "p"), ("Trho", "p"),
                                               ("pT", None)])
def test_the_family_is_the_one_running_through_the_dome(diagram_type, key):
    assert dome_key(PropertyDiagram("R290", diagram_type).diagram_type) == key


def test_each_isotherm_is_labelled_next_to_the_bubble_and_the_dew_line():
    diagram = _chart()
    labels = _dome(diagram)
    frame = Frame.from_axes(diagram.scene.axes, default_plot_size_pt(diagram.spec))
    fluid = diagram.fluid
    zero = [labels["iso/T/273.15/label/dome/" + side] for side in ("liquid", "vapour")]
    assert [t.text for t in zero] == ["0", "0"]   # rails: the bare value
    for label, Q, sign in zip(zero, (0.0, 1.0), (1.0, -1.0)):
        end = fluid.state_point("T", 273.15, "Q", Q)
        ex, ey = (float(v[0]) for v in frame.to_pt([end.h / 1e3], [end.p / 1e5]))
        lx, ly = (float(v[0]) for v in frame.to_pt([label.x], [label.y]))
        half_w = 0.5 * text_size_pt(label.text, label.style)[0]
        # On the isotherm (horizontal in the dome of a pure fluid), DOME_GAP_PT inside the end
        assert ly == pytest.approx(ey, abs=1e-6)
        assert sign * (lx - ex) == pytest.approx(DOME_GAP_PT + half_w, abs=1e-6)


def test_the_labels_of_a_blend_follow_its_sloped_isotherms():
    diagram = _chart("HEOS::R32[0.5]&R1234yf[0.5]")
    labels = _dome(diagram)
    label = labels["iso/T/273.15/label/dome/liquid"]
    dx, dy = label.direction
    assert dy < 0.0 < dx   # the pressure falls from the bubble to the dew point


def test_isobars_are_labelled_in_a_T_s_chart():
    diagram = _chart("Water", "Ts", "p")
    assert any(i.endswith("/dome/liquid") and i.startswith("iso/p/") for i in _dome(diagram))


def test_labels_that_do_not_fit_near_the_critical_point_are_left_out():
    # R290: critical at 96.7 deg C. At 96 deg C the isotherm crosses the dome in about 23 pt, room for
    # one label but not two; at 96.6 deg C in 12 pt, room for none.
    diagram = _chart(digits=6)
    diagram.set_lines("T", values=[0.0, 96.0, 96.6], labels=True)
    labels = _dome(diagram)
    assert {i for i in labels if i.startswith("iso/T/273.15/")} == {"iso/T/273.15/label/dome/liquid",
                                                                     "iso/T/273.15/label/dome/vapour"}
    assert [i for i in labels if i.startswith("iso/T/369.15/")] == ["iso/T/369.15/label/dome/liquid"]
    assert not any(i.startswith("iso/T/369.75/") for i in labels)


def test_the_labels_do_not_overlap_and_keep_clear_of_a_cycle():
    diagram = _chart(mode="edge")
    diagram.set_default_lines(labels=True)
    diagram.add_cycle("heat pump", [{"p": 3.0, "T": 0.0}, {"p": 15.0, "via": "compression", "eta_is": 0.7},
                                    {"p": 15.0, "Q": 0.0}, {"p": 3.0, "via": "isenthalpic"}])
    labels = list(_dome(diagram).values())
    assert labels
    frame = Frame.from_axes(diagram.scene.axes, default_plot_size_pt(diagram.spec))
    states = diagram.scene["cycle/heat pump/states"]
    sx, sy = frame.to_pt(states.x, states.y)
    for label in labels:
        lx, ly = (float(v[0]) for v in frame.to_pt([label.x], [label.y]))
        assert min(math.hypot(lx - a, ly - b) for a, b in zip(sx, sy)) > 12.0


def test_lines_without_labels_get_none_in_the_dome():
    diagram = _chart()
    diagram.set_lines("T", num=8, rounding=True, labels=False)
    assert _dome(diagram) == {}
