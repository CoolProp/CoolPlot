# PDF, print and papers

```python
diagram.settings = diagram.settings.with_(page={"width_pt": 252, "height_pt": 190})   # one journal column
diagram.save("R290_ph.pdf")                        # vector PDF, fonts embedded as TrueType

from coolplot import save_pdf
save_pdf("report.pdf", [diagram, other_diagram, chart], metadata={"Author": "Heat pump team"})
```

`settings="publication"` is a preset for this: more points per line, the
black and white `print` theme, and a page of 252 by 189 pt.

What the PDF of the matplotlib backend guarantees:

* The page has the size of `settings.page`, and font sizes are in
  points, so a figure placed at 100 % in a document has exactly the type
  sizes of the theme. Set the page to the column or text width of the
  document instead of scaling the figure there.
* Fonts are embedded as TrueType (or `save(..., pdf_fonts="type3")`), as
  journals and print shops expect. Texts stay text: they can be selected,
  searched and edited, labels with a halo included.
* Colours are exactly those of the theme, as sRGB. There is no CMYK and
  no colour profile; print shops convert sRGB, or convert the PDF
  yourself (for example with Ghostscript) if a CMYK file is required.
* The same chart gives the same file (no date, no version strings), and
  the chart title becomes the PDF title. `save_pdf` writes one chart per
  page, each at its own page size.
* EPS and PS embed TrueType fonts the same way.

## Fonts

Matplotlib cannot embed fonts installed as CFF OpenType (many .otf
files, often Inter) as TrueType. Such a font is left out of the file
with a warning naming it and the font used instead; the window keeps the
original. Install the .ttf files of the font, or name them with
`Font(files=...)`, to keep it. Font collections (.ttc, as on macOS)
embed fine. `MatplotlibRenderer(strict_fonts=True)` raises instead of
replacing a font, and `renderer.fonts_used(pdf=True)` lists the fonts a
PDF gets, for print work where a replaced font must not slip through.

## Other formats

`save("chart.svg")` writes SVG and `save("chart.html")` a web page,
both without any dependency. `diagram.draw(PlotlyRenderer())` gives a
plotly figure (`pip install "coolplot[plotly]"`; `renderer.figure`,
`renderer.save("chart.html")`), and that renderer writes PDF and PNG too
when kaleido and Chrome are installed (`pip install "coolplot[images]"`).
