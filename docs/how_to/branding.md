# Logo, references and watermark

A chart that leaves your hands should say where it comes from: who made
it, and which equation of state the properties follow. `Settings.branding`
adds both, the way printed charts do: a small badge in one corner of the
plot area and, if you like, a faint picture behind the lines.

```python
from coolplot import PropertyDiagram

diagram = PropertyDiagram("R290", "ph", units="engineering", tp_limits="ACHP")
diagram.set_default_lines(labels=True)
diagram.settings = diagram.settings.with_(branding={
    "logo": ("logo.svg", "logo.png"),       # variants of one picture, see below
    "logo_width_pt": 60,
    "references": "short",                  # "R290: Lemmon et al. (2009)"
    "versions": True,                       # "CoolProp 8.0.0, CoolPlot 1.2.0"
    "lines": ("example.com | 2026-10-19",),
    "watermark": ("mark.svg", "mark.png"),
})
diagram.save("R290_ph.pdf")
```

## The badge

From top to bottom: the logo, the references, the versions line and your
own `lines`. `location="auto"` (the default) puts it into the corner
where it covers the fewest points of the drawn lines; name a corner
("upper left", "upper right", "lower left", "lower right") to fix it.
Rail and edge labels keep clear of the badge; inline and margin labels
do not. The badge and a legend inside the plot area are given their
corners together: a corner you name is kept, and "auto" takes the
emptiest of the others (preferring corners without cycles), so the two
share a corner only when you name the same one for both. Every backend
draws the badge at the same size, the one the label layout keeps clear;
the text widths are estimated, generously for common sans-serif fonts.

The background has the colour of the plot area at `background_alpha`
(0.85), so lines under the badge stay faintly visible; `frame=False`
removes the outline. The text uses the font family of the tick labels at
`font_size_pt` (6 pt), times the page's `font_scale`.

## References

`references="short"` names first author and year, `"full"` adds journal,
volume and pages. They come from CoolProp itself: the BibTeX key of each
equation of state (`CoolProp.CoolProp.get_BibTeXKey(fluid, "EOS")`) and
the bibliography that ships in the CoolProp package.

| Fluid | Lines |
|---|---|
| a pure fluid | its equation of state |
| a mixture (`"R407C.mix"`, `"R32[0.7]&R125[0.3]"`) | its name and composition, then each component, then "Mixture model:" with the references of the fitted binary pairs |
| humid air (psychrometric charts) | ASHRAE RP-1485 (Herrmann, Kretzschmar and Gatley) |
| REFPROP, Peng-Robinson, SRK, incompressibles | the name of the backend, no reference; the fractions of a mixture or solution ("MEG 30 % by mass") |

The first line of a mixture names it and gives its composition, since
1.4:

| Fluid | First line |
|---|---|
| `"R407C.mix"` | R407C: R32 23 %, R125 25 %, R134a 52 % by mass |
| `"R32[0.697616]&R125[0.302384]"` | R410A: R32 50 %, R125 50 % by mass |
| `"R32[0.2]&R125[0.8]"` | Mixture: R32 20 %, R125 80 % by mole |

A mixture given by its fractions carries the name of the predefined
blend of CoolProp with the same components and a composition within half
a percent (by mass); otherwise it is called "Mixture". Refrigerant blends
with an R number are shown by mass, as the R number is defined (ASHRAE
Standard 34); other mixtures in the basis of their fractions, which is
by mole for fluid strings.

`coolplot.thermo.references.fluid_references` returns the same lines for
use elsewhere, for example in a report.

## Pictures

Logos and watermarks are PNG or SVG files, given as file names or
`data:` URIs. Give the same picture in both formats when you can: the
SVG writer embeds the first variant (an SVG logo stays sharp at any
size), while matplotlib, which writes PNG and PDF, can only draw a PNG.
A logo given only as SVG is left out of PNG and PDF files with a
warning. PDF files embed the PNG with all its pixels, so a PNG of about
2000 pixels across is sharp in print.

Text in an SVG logo should be converted to outlines (paths): a viewer
without the logo's font would draw the text in another font.

The watermark is centred in the plot area, `watermark_width` (0.5) of its
width wide but never taller than 0.8 of its height, at
`watermark_opacity` (0.06). Opaque white parts of a picture stay white,
also over grid lines; a watermark of one colour on a transparent
background works best.

## Backends

| Backend | Badge and watermark |
|---|---|
| matplotlib: PNG, PDF, windows | drawn |
| matplotlib: PS and EPS | badge drawn with an opaque background and the logo's transparent pixels filled with that background colour; the watermark is left out with a warning (PostScript has no transparency) |
| SVG writer, web renderer (`WebRenderer`) | drawn |
| coolplot-core 1.5: composer, SVG writer, PDF writer (`PdfRenderer`) | badge of text lines drawn; a chart with a logo or a watermark is composed and written by Python (`PdfRenderer` leaves them out with a warning) |
| plotly, JavaScript writer (`scene_page`) | badge of text lines drawn (plotly centres each line in its line height, it has no baseline alignment); logo and watermark left out with a warning |

## In the gallery

A company chart with its own theme colours, logo, references, versions,
web address and brandmark as watermark (Clean Heat Partners):
{doc}`../gallery/branding_chp`.
