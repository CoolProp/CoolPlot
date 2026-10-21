# -*- coding: utf-8 -*-
"""Write the golden files the C++ tests compare against, from the Python reference.

Run from the repository root with CoolPlot installed:
    python cpp/tests/data/make_data.py
"""
import json
import os
import sys

from coolplot import PropertyDiagram, PsychrometricChart
from coolplot.compose.builder import compose
from coolplot.engine import plan
from coolplot.render.svg import SvgRenderer
from coolplot.scene import Scene, item_to_dict
from coolplot.style.theme import get_theme
from coolplot.testing import conformance_scene

HERE = os.path.dirname(os.path.abspath(__file__))


def dump(name, data):
    with open(os.path.join(HERE, name), "w", encoding="ascii", newline="\n") as f:
        json.dump(data, f, sort_keys=True, allow_nan=False, separators=(",", ":"))
        f.write("\n")


def dump_svg(name, scene, **options):
    renderer = SvgRenderer(**options)
    renderer.sync(scene)
    with open(os.path.join(HERE, name), "w", encoding="ascii", newline="\n") as f:
        f.write(renderer.to_svg())


def curve_record(request, curve):
    return {"request": {"item_id": request.item_id, "key": request.key, "value_SI": request.value_SI,
                        "points": request.points, "labels": request.labels, "anchor_SI": request.anchor_SI},
            "curve": curve.to_dict()}


def legacy(chart):
    """The chart with edge labels and the legend outside on the right, the defaults before 1.2."""
    if chart.settings.labels.mode == "rails":
        chart.settings = chart.settings.with_(labels={"mode": "edge"})
    theme = chart.theme
    if theme.axes.legend.location == "auto":
        chart.theme = theme.with_(axes=theme.axes.with_(legend=theme.axes.legend.with_(location="outside right")))
    return chart


def compose_case(name, chart, plot_size_pt=None, previous=None):
    """The input of the composer and the scene the Python composer makes of it."""
    if not name.startswith("compose_rails_"):
        legacy(chart)
    spec = chart.spec
    domain = chart.engine.domain(spec)
    curves = chart.engine.curves(spec, domain, plan(spec, domain))
    cycles = [chart.engine.cycle(spec, c) for c in spec.cycles]
    items, axes = compose(spec, domain, curves, plot_size_pt, previous, cycles)
    scene = Scene(axes, items)
    data = {
        "spec": spec.to_dict(),
        "domain": {"tp_box": list(domain.tp_box), "ranges_SI": {k: list(v) for k, v in domain.ranges_SI}},
        "curves": [curve_record(r, c) for r, c in curves],
        "cycles": [{"states": {str(n): s.to_dict() for n, s in states.items()},
                    "chains": [[s.to_dict() for s in chain] for chain in chains]} for states, chains in cycles],
        "plot_size_pt": None if plot_size_pt is None else list(plot_size_pt),
        "previous_labels": None if previous is None else [item_to_dict(t) for t in previous.values()],
    }
    # "scene" is the record of the contract (items in drawing order), which
    # the composer has to match; "scene_order" holds the same items in scene
    # order, which the SVG writers get (the legend follows that order)
    dump(name + ".json", {"input": data, "scene": scene.to_dict(),
                          "scene_order": scene.to_dict(in_draw_order=False)})
    dump_svg(name + ".svg", scene)
    return scene


def main():
    # In scene order, so that the writers give the legend in the same order
    dump("conformance_scene.json", conformance_scene().to_dict(in_draw_order=False))
    dump_svg("conformance_scene.svg", conformance_scene())
    dump_svg("conformance_scene_small.svg", conformance_scene(), width=640, height=480, margins=(50, 10, 30, 40),
             id_prefix="2 charts/one page")
    # Autoscaled axes, a legend in every corner, a narrow log range
    from dataclasses import replace
    from coolplot.scene import AxesSpec, Line, Markers
    scene = conformance_scene()
    for location in ("upper left", "lower right"):
        legend = replace(scene.axes.style.legend, location=location)
        scene.set_axes(replace(scene.axes, style=replace(scene.axes.style, legend=legend)))
        dump_svg("conformance_legend_%s.svg" % location.replace(" ", "_"), scene)
    dump_svg("autoscale.svg", Scene(AxesSpec(y_log=True), [
        Line(id="a", x=[1.0, 2.0, 3.0], y=[0.5, 5.0, 50.0]),
        Markers(id="b", x=[4.0], y=[float("nan")]),
        Line(id="hidden", visible=False, x=[-100.0, 1000.0], y=[1e-6, 1e9])]))
    dump_svg("narrow_log.svg", Scene(AxesSpec(y_log=True, x_limits=(1.5, 1.9), y_limits=(1.5, 1.9)),
                                     [Line(id="a", x=[1.5, 1.9], y=[1.5, 1.9])]))

    # Few points per line (the "interactive" preset) keep the files small;
    # the composer does not care how many there are.
    diagram = PropertyDiagram("R290", "ph", tp_limits="ACHP", settings="interactive")
    diagram.set_default_lines(labels=True)
    diagram.add_cycle("heat pump", [{"p": 3.0, "T": 0.0}, {"p": 15.0, "via": "compression", "eta_is": 0.7},
                                    {"p": 15.0, "Q": 0.0}, {"p": 3.0, "via": "isenthalpic"}])
    scene = compose_case("compose_r290_ph", diagram)
    # The same chart laid out for a renderer's plot size, with the labels of
    # the first layout given as the previous ones
    previous = {item.id: item for item in scene if item.role == "isoline_label"}
    compose_case("compose_r290_ph_sized", diagram, (400.0, 300.0), previous)

    blend = PropertyDiagram("HEOS::R32[0.7]&R125[0.3]", "Ts", tp_limits="ACHP", settings="print")
    blend.settings = blend.settings.with_(calc="interactive", labels={"mode": "margin"})
    blend.set_default_lines(labels=True)
    compose_case("compose_blend_ts_margin", blend)

    inline = PropertyDiagram("R290", "hs", units="SI", tp_limits="DEF", settings="interactive")
    inline.settings = inline.settings.with_(labels={"mode": "inline", "show_units": False, "digits": 3},
                                            page={"font_scale": 1.5})
    inline.set_default_lines(labels=True)
    inline.set_lines("T", num=5, labels=True)
    inline.set_line_style("T", color="purple", dash="dashed")
    inline.title = "Propane h-s"
    compose_case("compose_r290_hs_inline", inline)

    chart = PsychrometricChart(T_range=(-10, 45), W_range=(0, 25), settings="interactive")
    chart.set_default_lines()
    chart.add_cycle("Air conditioning", [{"T": 32, "RH": 50}, {"T": 13, "RH": 95}, {"T": 20, "W": 8.9}], closed=False)
    compose_case("compose_psychrometric", chart)

    # State labels: after the numbers on one process, alone (numbers hidden)
    # on an outline whose other states get no text
    labelled = PsychrometricChart(T_range=(-10, 45), W_range=(0, 25), settings="interactive")
    labelled.set_default_lines()
    labelled.add_cycle("Air conditioning", [{"T": 32, "RH": 50}, {"T": 13, "RH": 95}, {"T": 20, "via": "sensible"}],
                       closed=False, labels={2: "ADP 11.2 deg C", 3: "+7.1 kJ/kg"})
    labelled.add_cycle("Comfort zone", [{"T": 20, "RH": 30}, {"T": 26, "RH": 30}, {"T": 26, "RH": 60},
                                        {"T": 20, "RH": 60}], numbers=False, labels={3: "comfort"})
    compose_case("compose_psychrometric_labels", labelled)

    # The Mollier h,x chart: isotherms, x and phi, a process with labels
    mollier = PsychrometricChart(T_range=(-10, 45), W_range=(0, 25), settings="interactive", style="mollier")
    mollier.set_default_lines()
    mollier.add_cycle("Air conditioning", [{"T": 32, "RH": 50}, {"T": 13, "RH": 95}, {"T": 20, "via": "sensible"}],
                      closed=False, labels={2: "coil"})
    compose_case("compose_mollier", mollier)

    # The saturation curve without lines of constant quality (drawn since 1.2)
    bare = PropertyDiagram("R290", "Ts", tp_limits="ACHP", settings="interactive")
    bare.set_lines("p", num=6, labels=True)
    compose_case("compose_r290_ts_saturation_only", bare)

    # Isentropes through the saturated vapour every 10 K and isochores through
    # wet states every 20 K, labelled by their saturation temperature;
    # isotherms through the saturated vapour every 2 bar, labelled by their
    # own values (the default)
    anchored = PropertyDiagram("R290", "ph", tp_limits="ACHP", settings="interactive")
    anchored.set_lines("Q", num=6, labels=True)
    anchored.set_lines("s", at_saturation={"T": 10, "range": (-40, 60), "label": "saturation"}, labels=True)
    anchored.set_lines("rho", at_saturation={"T": 20, "Q": 0.5, "label": "saturation"}, labels=True)
    anchored.set_lines("T", at_saturation={"p": 2}, labels=True)
    compose_case("compose_r290_ph_anchored", anchored)

    # Labels in the colour of their lines, on the dark theme (the halo in the
    # dark surface colour)
    coloured = PropertyDiagram("R290", "ph", tp_limits="ACHP", settings="interactive")
    coloured.theme = get_theme("dark").with_(isoline_label_color="line")
    coloured.set_default_lines(labels=True)
    compose_case("compose_r290_ph_line_labels", coloured)

    rails_cases()


def rails(chart, legend="auto"):
    """The chart with labels on rails and the legend at ``legend``."""
    chart.settings = chart.settings.with_(labels={"mode": "rails"})
    theme = chart.theme
    chart.theme = theme.with_(axes=theme.axes.with_(legend=theme.axes.legend.with_(location=legend)))
    return chart


def rails_cases():
    """Labels on rails (1.2): outer and inner rails, thinning, second rails, line ends, stability."""
    def r290():
        d = PropertyDiagram("R290", "ph", tp_limits="ACHP", settings="interactive")
        d.set_lines("T", values=list(range(-40, 181, 10)), labels=True)
        d.set_lines("s", values=[x / 100.0 for x in range(75, 301, 25)], labels=True)
        d.set_lines("rho", values=[1, 2, 5, 10, 20, 50, 100, 200, 500], labels=True)
        d.set_lines("Q", values=[x / 10.0 for x in range(0, 11)], labels=True)
        d.add_cycle("Heat pump", [{"p": 3.0, "T": 0.0}, {"p": 15.0, "via": "compression", "eta_is": 0.7},
                                  {"p": 15.0, "Q": 0.0}, {"p": 3.0, "via": "isenthalpic"}])
        return rails(d)

    size = (600.0, 420.0)
    chart = r290()
    scene = compose_case("compose_rails_r290_ph", chart, size)
    # A state moved, laid out with the first layout as the previous one:
    # labels that stay are the same items, and families keep their rails
    previous = {item.id: item for item in scene if item.role == "isoline_label"}
    chart.move_cycle_state("Heat pump", 2, 690.0, 15.0)
    compose_case("compose_rails_r290_ph_moved", chart, size, previous)
    # A narrow chart: whole levels of values are dropped
    compose_case("compose_rails_r290_ph_narrow", r290(), (260.0, 420.0))
    # A legend outside on the right leaves the right rail free
    compose_case("compose_rails_r290_ph_outside_legend", rails(r290(), "outside right"), size)
    # Relative humidity on two rails, enthalpy on the right, line ends
    psy = rails(PsychrometricChart(T_range=(-10, 45), W_range=(0, 25), settings="interactive"))
    psy.set_default_lines()
    psy.add_cycle("Air conditioning", [{"T": 32, "RH": 50}, {"T": 13, "RH": 95}, {"T": 20, "via": "sensible"}],
                  closed=False)
    compose_case("compose_rails_psychrometric", psy, size)
    mollier = rails(PsychrometricChart(T_range=(-10, 45), W_range=(0, 25), settings="interactive", style="mollier"))
    mollier.set_default_lines()
    compose_case("compose_rails_mollier", mollier, size)
    # A family labelled by its saturation states keeps its full labels and its plain legend
    anchored = rails(PropertyDiagram("R290", "ph", tp_limits="ACHP", settings="interactive"))
    anchored.set_lines("rho", at_saturation={"T": 20, "Q": 0.5, "label": "saturation"}, labels=True)
    anchored.set_lines("T", at_saturation={"p": 2}, labels=True)
    compose_case("compose_rails_r290_ph_anchored", anchored, size)


if __name__ == "__main__":
    sys.exit(main())
