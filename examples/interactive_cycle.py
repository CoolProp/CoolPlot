# -*- coding: utf-8 -*-
"""
Interactive log(p)-h chart with a refrigeration cycle
=====================================================


Drag the sliders to change the evaporating and condensing temperatures,
or drag a state of the cycle with the mouse. Only the cycle is
recalculated and redrawn; the isolines come from the cache and their
matplotlib artists are never touched, and isoline labels only move when
the cycle comes too close. Zoom and pan with the toolbar: the labels
follow. Move the mouse over the chart to read the full state under the
cursor.

Run with:  python examples/interactive_cycle.py
"""
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider

from coolplot import PropertyDiagram
from coolplot.interaction import Interaction
from coolplot.render.mpl import MatplotlibRenderer
from coolplot.thermo.cycles import simple_compression

FLUID = "HEOS::R290"


def main():
    diagram = PropertyDiagram(FLUID, "ph", units="engineering", tp_limits="ACHP")
    diagram.title = "R290 - drag the sliders"
    diagram.set_lines("Q", num=11, labels=True)
    diagram.set_lines("T", num=15, rounding=True, labels=True)
    diagram.set_lines("s", num=12, rounding=True, labels=True)

    fig, ax = plt.subplots(figsize=(9, 7))
    # The figure belongs to this script, so leave room for the legend that
    # the default theme puts outside the axes on the right.
    fig.subplots_adjust(bottom=0.22, right=0.78)
    renderer = MatplotlibRenderer(ax=ax)
    status = fig.text(0.01, 0.01, "", family="monospace", fontsize=8)
    readout = fig.text(0.01, 0.97, "", family="monospace", fontsize=8)

    ax_evap = fig.add_axes((0.15, 0.10, 0.7, 0.03))
    ax_cond = fig.add_axes((0.15, 0.05, 0.7, 0.03))
    T_evap = Slider(ax_evap, "T_evap / \u00b0C", -40.0, 15.0, valinit=-5.0)
    T_cond = Slider(ax_cond, "T_cond / \u00b0C", 20.0, 70.0, valinit=40.0)

    def redraw(_=None):
        cycle = simple_compression(diagram.fluid, T_evap.val, T_cond.val, name="Heat pump")
        diagram.add_cycle(cycle)   # replaces the cycle of the same name
        report = renderer.sync(diagram.update_scene(renderer.plot_size_pt()))
        status.set_text("COP heating {0:.2f} | last redraw: {1} added, {2} updated, {3} untouched".format(
            cycle.result["COP_heating"], len(report.added), len(report.updated), report.unchanged))

    def show_state(state, event):
        if state is None:
            return
        readout.set_text("T = {0:.1f} \u00b0C, p = {1:.2f} bar, h = {2:.1f} kJ/kg, s = {3:.3f} kJ/kg/K".format(
            state.T - 273.15, state.p * 1e-5, state.h * 1e-3, state.s * 1e-3))
        fig.canvas.draw_idle()

    # Zoom, pan, hover and dragging cycle states are handled by Interaction
    Interaction(diagram, renderer, on_hover=show_state)

    T_evap.on_changed(redraw)
    T_cond.on_changed(redraw)
    redraw()
    plt.show()


if __name__ == "__main__":
    main()
