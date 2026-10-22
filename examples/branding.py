# -*- coding: utf-8 -*-
"""
A chart with a logo, references and a watermark
===============================================

A chart that leaves your hands should say who made it and which equation
of state its properties follow. ``Settings.branding`` adds a badge in a
corner of the plot area, from top to bottom: a logo, the references of
the fluid (here in full, with journal, volume and pages, taken from
CoolProp's own bibliography), the versions of CoolProp and CoolPlot and
lines of your own; and a faint watermark behind the lines.

The badge takes the corner where it covers the fewest lines, and the
labels keep clear of it. The logo here is a small SVG picture written into
the script as a ``data:`` URI; a file name works the same way. The
matplotlib backend needs a PNG variant of a picture, the SVG writer used
here takes the SVG.

Run with:  python examples/branding.py
Writes branding.svg.
"""
import base64

from coolplot import PropertyDiagram
from coolplot.render.svg import SvgRenderer
from coolplot.thermo.cycles import simple_compression
from coolplot.thermo.references import fluid_references

# A made-up logo: a saturation dome with a cycle in it, and two bars for a name
LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 40">
<path d="M4 36 C 14 2, 34 2, 44 36" fill="none" stroke="#2a78d6" stroke-width="4"/>
<rect x="16" y="14" width="18" height="14" fill="none" stroke="#c0392b" stroke-width="3"/>
<rect x="54" y="10" width="62" height="6" fill="#1b2631"/>
<rect x="54" y="22" width="44" height="6" fill="#1b2631"/>
</svg>"""
logo = "data:image/svg+xml;base64," + base64.b64encode(LOGO_SVG.encode("ascii")).decode("ascii")

diagram = PropertyDiagram("HEOS::R32", "ph", units="engineering", tp_limits="ACHP")
diagram.title = "R32 heat pump"
diagram.set_lines("Q", num=11, labels=True)
diagram.set_lines("T", num=10, rounding=True, labels=True)
diagram.set_lines("s", num=8, rounding=True, labels=True)
diagram.add_cycle(simple_compression(diagram.fluid, T_evap_C=0.0, T_cond_C=50.0))
diagram.settings = diagram.settings.with_(branding={
    "logo": (logo,),
    "logo_width_pt": 70,
    "references": "full",
    "versions": True,
    "lines": ("Example Engineering | heat pump study",),
    "watermark": (logo,),
})

diagram.draw(SvgRenderer(width=900, height=650)).save("branding.svg")
for line in fluid_references(diagram.spec.fluid, "full"):
    print(line)
