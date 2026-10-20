# Figures for a paper

A chart as a vector PDF at the column width of the journal, with the
fonts embedded, the colours exact and a black and white version for
print.

## Page size and type size

```python
from coolplot import PropertyDiagram
from coolplot.thermo.cycles import rankine

diagram = PropertyDiagram("Water", "Ts", units="engineering", tp_limits="ORC",
                          settings="publication")
diagram.set_default_lines(labels=True)
diagram.add_cycle(rankine("Water", p_high_Pa=40e5, p_low_Pa=0.1e5, T_live_C=400))
diagram.settings = diagram.settings.with_(page={"width_pt": 252, "height_pt": 190})
diagram.save("rankine.pdf")
```

The `"publication"` preset uses more points per line and the black and
white `print` theme, in which the line families differ by dash pattern.
The page is set to the column width of the journal (252 pt is 3.5 in);
placed at 100 % in the manuscript, the figure then has exactly the type
sizes of the theme, 8 pt for tick labels. Do not scale the figure in the
document: set the page instead.

## Colour, with the same fonts

```python
diagram.theme = "default"
diagram.settings = diagram.settings.with_(page={"font_scale": 1.1})
diagram.save("rankine_colour.pdf")
```

The colours of the `default` theme are checked for readers with a colour
vision deficiency; see {doc}`../explanation/colours`.

## Fonts

A journal that asks for Times or Helvetica gets them through the theme:

```python
from coolplot.style.theme import DEFAULT
from coolplot.style.values import Font
times = Font(family=("Times New Roman", "Nimbus Roman", "serif"), size_pt=8.0)
diagram.theme = DEFAULT.with_(name="paper", axes=DEFAULT.axes.with_(
    tick_label=DEFAULT.axes.tick_label.with_(font=times),
    axis_label=DEFAULT.axes.axis_label.with_(font=times.with_(size_pt=9.0))))
```

The first installed family of the list wins. The PDF embeds the fonts as
TrueType, as print shops expect; `MatplotlibRenderer(strict_fonts=True)`
refuses to save when a font would be replaced, see {doc}`../how_to/pdf_print`.

## Several figures in one file

```python
from coolplot import save_pdf
save_pdf("figures.pdf", [diagram, other_diagram], metadata={"Author": "Thermodynamics group"})
```

One chart per page, each at its own page size, with no date in the file:
the same charts give the same bytes, so a figure under version control
only changes when the chart does.
