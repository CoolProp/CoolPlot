# -*- coding: utf-8 -*-
"""An interactive chart in the browser, without any web framework.

Starts a small development server and prints its address. Open it in a
browser: drag the states of the cycle, drag empty space to pan, use the
mouse wheel to zoom. Only the changed SVG elements travel to the browser.

Run with:  python examples/web_app.py   (stop with Ctrl+C)
"""
from coolplot import PropertyDiagram
from coolplot.interaction import Interaction
from coolplot.render.web import WebRenderer, WebServer
from coolplot.thermo.cycles import simple_compression

diagram = PropertyDiagram("HEOS::R290", "ph", units="EUR", tp_limits="ACHP")
diagram.title = "R290 - drag the states"
diagram.set_isolines("Q", num=11, labels=True)
diagram.set_isolines("T", num=12, rounding=True, labels=True)
diagram.set_isolines("s", num=10, rounding=True, labels=True)
diagram.add_cycle(simple_compression(diagram.fluid, T_evap_C=-5.0, T_cond_C=45.0, name="Heat pump"))

renderer = WebRenderer(width=1000, height=700)
Interaction(diagram, renderer)    # zoom, pan and dragging states
renderer.sync(diagram.update_scene(renderer.plot_size_pt()))

server = WebServer(renderer, title="CoolPlot")
print("Open", server.url)
server.serve_forever()
