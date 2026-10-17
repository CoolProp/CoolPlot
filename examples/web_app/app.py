# -*- coding: utf-8 -*-
"""An interactive chart in the browser, without any web framework.

Starts a small development server and prints its address. Open it in a
browser: drag the states of the cycle, drag empty space to pan, use the
mouse wheel to zoom. Only the changed SVG elements travel to the browser.

The server (server.py, next to this file) is a starting point for an
application of your own; the library only provides the renderer.

Run with:  python examples/web_app/app.py   (stop with Ctrl+C)
"""
import os
import sys

from coolplot import PropertyDiagram
from coolplot.interaction import Interaction
from coolplot.render.web import WebRenderer
from coolplot.thermo.cycles import simple_compression

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from server import WebServer  # noqa: E402

diagram = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP")
diagram.title = "R290 - drag the states"
diagram.set_lines("Q", num=11, labels=True)
diagram.set_lines("T", num=12, rounding=True, labels=True)
diagram.set_lines("s", num=10, rounding=True, labels=True)
diagram.add_cycle(simple_compression(diagram.fluid, T_evap_C=-5.0, T_cond_C=45.0, name="Heat pump"))

renderer = WebRenderer(width=1000, height=700)
Interaction(diagram, renderer)    # zoom, pan and dragging states
renderer.sync(diagram.update_scene(renderer.plot_size_pt()))

server = WebServer(renderer, title="CoolPlot")
print("Open", server.url)
server.serve_forever()
