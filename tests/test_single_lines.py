# -*- coding: utf-8 -*-
"""Single lines drawn on top of the families (Chart.add_line), issue #32."""
import json

import numpy as np
import pytest

pytest.importorskip("CoolProp")

from coolplot import DiagramSpec, LineSpec, LineStyle, PropertyDiagram, PsychrometricChart  # noqa: E402
from coolplot.engine import plan  # noqa: E402

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


def _co2():
    chart = PropertyDiagram("CO2", "ph", units="engineering")
    chart.set_default_lines(labels=True, rounding=True)
    return chart


def _items(chart):
    return {item.id: item for item in chart.update_scene()}


def test_a_highlighted_isotherm_keeps_the_family():
    chart = _co2()
    isotherms = len([r for r in plan(chart.spec, chart.engine.domain(chart.spec)) if r.key == "T"])
    name = chart.add_line("T", 22)
    assert name == "T=22 \u00b0C"
    requests = plan(chart.spec, chart.engine.domain(chart.spec))
    assert len([r for r in requests if r.key == "T" and r.item_id.startswith("iso/")]) == isotherms
    line = next(r for r in requests if r.item_id == "line/" + name)
    assert line.value_SI == pytest.approx(295.15)
    items = _items(chart)
    family = next(i for i in items.values() if i.group == "iso/T")
    highlight = items["line/" + name]
    # The family's colour at twice its width, drawn above the dome and below the labels
    assert highlight.role == "line" and highlight.legend == name
    assert highlight.style.color == family.style.color
    assert highlight.style.width_pt == pytest.approx(2.0 * family.style.width_pt)
    assert highlight.z_order == 3.0
    assert items["line/" + name + "/label"].text == name
    assert items["line/" + name + "/label"].role == "line_label"
    # set_lines leaves the line alone
    chart.set_lines("T", num=5)
    assert "line/" + name in _items(chart)


def test_a_line_of_an_axis_quantity_spans_the_plot():
    chart = _co2()
    chart.add_line("p", 130, name="Burst disk", line_style=LineStyle(color="red", width_pt=2.0))
    scene = chart.update_scene()
    line = scene["line/Burst disk"]
    assert list(line.y) == [130.0, 130.0]
    assert tuple(line.x) == tuple(scene.axes.x_limits)
    assert line.style.color == "#ff0000" and line.style.width_pt == 2.0
    label = scene["line/Burst disk/label"]
    assert label.text == "p=130 bar" and label.direction == (1.0, 0.0) and label.y == 130.0
    # Lines of an axis quantity need no curve
    assert all(not r.item_id.startswith("line/") for r in plan(chart.spec, chart.engine.domain(chart.spec)))


def test_a_line_outside_the_region_widens_the_axes():
    chart = _co2()
    assert chart.update_scene().axes.x_limits[1] < 1000.0
    chart.add_line("h", 1000, label="h max")
    scene = chart.update_scene()
    assert scene.axes.x_limits[1] > 1000.0
    line = scene["line/h=1000 kJ/kg"]
    assert list(line.x) == [1000.0, 1000.0] and tuple(line.y) == tuple(scene.axes.y_limits)
    assert scene["line/h=1000 kJ/kg/label"].text == "h max"


def test_a_zoom_window_keeps_the_line_and_drops_a_label_out_of_view():
    chart = _co2()
    chart.add_line("h", 900, name="Outside", label=True)
    chart.set_view(x_limits=(450, 600))
    items = _items(chart)
    assert "line/Outside" in items and "line/Outside/label" not in items
    assert items["line/Outside"].x[0] == 900.0


def test_labels_names_and_removal():
    chart = _co2()
    chart.add_line("T", 22, label=False)
    chart.add_line("T", 0, name="Evaporator", label="evap.")
    items = _items(chart)
    assert "line/T=22 \u00b0C" in items and "line/T=22 \u00b0C/label" not in items
    assert items["line/Evaporator/label"].text == "evap."
    # The same name replaces the line
    chart.add_line("T", 5, name="Evaporator")
    assert [line.value_SI for line in chart.spec.lines if line.name == "Evaporator"] == [278.15]
    chart.remove_line("Evaporator")
    chart.remove_line("not there")
    assert [line.name for line in chart.spec.lines] == ["T=22 \u00b0C"]
    assert not any(i.startswith("line/Evaporator") for i in _items(chart))


def test_units_of_the_value():
    chart = _co2()
    name = chart.add_line("p", 13e6, units="SI")
    assert name == "p=130 bar"
    assert chart.spec.lines[0].value_SI == 13e6


def test_bad_lines_are_refused():
    chart = _co2()
    with pytest.raises(ValueError, match="cannot be drawn"):
        chart.add_line("RH", 50)
    with pytest.raises(ValueError, match="between 0 and 1"):
        chart.add_line("Q", 1.5)
    with pytest.raises(ValueError, match="one value"):
        chart.add_line("T", [10, 20])
    with pytest.raises(ValueError, match="finite"):
        chart.add_line("T", float("nan"))
    with pytest.raises(ValueError, match="label"):
        chart.add_line("T", 10, label="")
    with pytest.raises(ValueError, match="unique"):
        DiagramSpec("CO2", lines=(LineSpec("a", "T", 300.0), LineSpec("a", "T", 310.0)))
    assert chart.spec.lines == ()


def test_the_spec_record_round_trips():
    chart = _co2()
    record = chart.spec.to_dict()
    assert "lines" not in record   # a chart without single lines writes the record as before
    chart.add_line("T", 22)
    chart.add_line("p", 130, name="Burst disk", line_style=LineStyle(color="red"), label="burst", points=50)
    record = json.loads(json.dumps(chart.spec.to_dict()))
    assert record["lines"][1] == {"name": "Burst disk", "key": "p", "value_SI": 13e6, "label": "burst",
                                  "line_style": record["lines"][1]["line_style"], "points": 50}
    assert DiagramSpec.from_dict(record) == chart.spec


def test_a_single_line_shares_its_curve_with_the_family():
    chart = _co2()
    chart.set_lines("T", values=[22], labels=True)
    chart.add_line("T", 22)
    domain = chart.engine.domain(chart.spec)
    family, single = [r for r in plan(chart.spec, domain) if r.key == "T"]
    assert chart.engine.cache_key(chart.spec, domain, family) == chart.engine.cache_key(chart.spec, domain, single)
    items = _items(chart)
    assert np.array_equal(items["iso/T/295.15"].x, items["line/T=22 \u00b0C"].x)


def test_a_psychrometric_chart():
    chart = PsychrometricChart(T_range=(-10, 45), W_range=(0, 25))
    chart.set_default_lines()
    chart.add_line("T", 26, name="Room")
    chart.add_line("RH", 60)
    items = _items(chart)
    assert list(items["line/Room"].x) == [26.0, 26.0]
    assert items["line/\u03c6=60 %"].role == "line"
    assert items["line/\u03c6=60 %/label"].text == "\u03c6=60 %"


def test_the_line_is_drawn(tmp_path):
    chart = _co2()
    chart.add_line("T", 22)
    chart.add_line("p", 130, name="Burst disk")
    path = tmp_path / "chart.svg"
    chart.save(str(path))
    svg = path.read_text(encoding="utf-8")
    assert "Burst disk" in svg and "p=130 bar" in svg
