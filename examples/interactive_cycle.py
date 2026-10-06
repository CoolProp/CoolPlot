# -*- coding: utf-8 -*-
"""Interactive log(p)-h chart with a refrigeration cycle.

Drag the sliders to change the evaporating and condensing temperatures.
Only the two cycle items are recalculated and redrawn; the isolines come
from the cache and their matplotlib artists are never touched. Move the
mouse over the chart to read the full state under the cursor.

Run with:  python examples/interactive_cycle.py
"""
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider

from CoolPlot import PropertyDiagram
from CoolPlot.render.mpl import MatplotlibRenderer
from CoolPlot.thermo import process_path, state_point

FLUID = "HEOS::R290"


def simple_cycle(fluid, T_evap_C, T_cond_C, dT_sh_K=5.0, eta_is=0.7):
    """States of a simple vapour compression cycle in SI units.

    Returns the states along the cycle path and the four corner states.
    """
    T_evap_K, T_cond_K = T_evap_C + 273.15, T_cond_C + 273.15
    p_evap_Pa = state_point(fluid, "T", T_evap_K, "Q", 1.0).p
    p_cond_Pa = state_point(fluid, "T", T_cond_K, "Q", 0.0).p

    evap_out = state_point(fluid, "p", p_evap_Pa, "T", T_evap_K + dT_sh_K)
    comp_out_is = state_point(fluid, "p", p_cond_Pa, "s", evap_out.s)
    h_comp_out_J_kg = evap_out.h + (comp_out_is.h - evap_out.h) / eta_is
    comp_out = state_point(fluid, "p", p_cond_Pa, "h", h_comp_out_J_kg)
    cond_out = state_point(fluid, "p", p_cond_Pa, "Q", 0.0)
    valve_out = state_point(fluid, "p", p_evap_Pa, "h", cond_out.h)

    path = (process_path(fluid, evap_out, comp_out, along=("p", "h"), steps=10)
            + process_path(fluid, comp_out, cond_out, along=("p", "h"), steps=20)
            + [valve_out]
            + process_path(fluid, valve_out, evap_out, along=("p", "h"), steps=10))
    return path, [evap_out, comp_out, cond_out, valve_out]


def main():
    diagram = PropertyDiagram(FLUID, "ph", units="EUR", tp_limits="ACHP")
    diagram.title = "R290 - drag the sliders"
    diagram.grid = True
    diagram.set_isolines("Q", num=11)
    diagram.set_isolines("T", num=15, rounding=True)
    diagram.set_isolines("s", num=12, rounding=True)

    fig, ax = plt.subplots(figsize=(9, 7))
    fig.subplots_adjust(bottom=0.22)
    renderer = MatplotlibRenderer(ax=ax)
    status = fig.text(0.01, 0.01, "", family="monospace", fontsize=8)
    readout = fig.text(0.01, 0.97, "", family="monospace", fontsize=8)

    ax_evap = fig.add_axes([0.15, 0.10, 0.7, 0.03])
    ax_cond = fig.add_axes([0.15, 0.05, 0.7, 0.03])
    T_evap = Slider(ax_evap, "T_evap / deg C", -40.0, 15.0, valinit=-5.0)
    T_cond = Slider(ax_cond, "T_cond / deg C", 20.0, 70.0, valinit=40.0)

    def redraw(_=None):
        path, corners = simple_cycle(diagram.fluid, T_evap.val, T_cond.val)
        diagram.set_process("cycle", path, corners)
        report = renderer.sync(diagram.update_scene())
        status.set_text("last redraw: {0} added, {1} updated, {2} untouched".format(
            len(report.added), len(report.updated), report.unchanged))

    def on_move(event):
        if event.inaxes is not ax or event.xdata is None:
            return
        try:
            s = diagram.state_at(event.xdata, event.ydata)
        except ValueError:
            return
        readout.set_text("T = {0:.1f} deg C, p = {1:.2f} bar, h = {2:.1f} kJ/kg, s = {3:.3f} kJ/kg/K".format(
            s.T - 273.15, s.p * 1e-5, s.h * 1e-3, s.s * 1e-3))
        fig.canvas.draw_idle()

    T_evap.on_changed(redraw)
    T_cond.on_changed(redraw)
    fig.canvas.mpl_connect("motion_notify_event", on_move)
    redraw()
    plt.show()


if __name__ == "__main__":
    main()
