# Themes and styles

Every visual property of a chart comes from a theme. The chart turns the
theme into concrete styles when it builds the picture, so a chart looks
the same whether matplotlib, the SVG writer or plotly draws it. Changing
the theme never recalculates properties; only the restyled items are
redrawn.

```python
diagram = PropertyDiagram("R290", "ph", units="engineering", theme="default")
diagram.theme = "dark"                                 # switch at any time
diagram.set_line_style("T", width_pt=1.0)              # one family, this chart only
```

| Theme | Use |
|-------|-----|
| `default` | Screen, light background. One colour per quantity, the same on every chart, checked for colour vision deficiencies. |
| `dark` | Screen, dark background. One colour per quantity, chosen and checked for the dark surface. |
| `print` | Black and white. Families differ by dash pattern only. |
| `coolpack` | The log(p),h-diagrams of CoolPack (DTU, late 1990s): Times on white, a dense grey grid, red isotherms, blue isentropes, green isochores, labels in the colour of their lines, no legend. |

In `default` and `dark`, isolines are thin reference lines in colour.
The saturation dome and cycles are drawn in ink, heavier and with a
casing, so they read as the subject of the chart. Text uses ink colours,
not series colours, unless a theme asks for labels in the colour of their
lines (`isoline_label_color`, below). Why the colours are what they are is
in {doc}`../explanation/colours`; every theme with its pictures and its
contrast and colour vision numbers is in the {doc}`../explanation/theme_catalog`.

## Customise

Three levels, from narrow to broad:

```python
# One family in one chart, any LineStyle field
diagram.set_line_style("s", dash="dashed")
diagram.set_line_style("s")                          # back to the theme

# A derived theme
from coolplot.style.theme import DEFAULT, Theme
mine = DEFAULT.with_(name="report", isoline=DEFAULT.isoline.with_(width_pt=0.5))
mine = mine.with_isoline_color("T", "darkred")       # pin a colour to a quantity
mine = mine.with_(isoline_label_color="line")        # each label in its line's colour
diagram.theme = mine

# Saved and loaded as JSON
import json
json.dump(mine.to_dict(), open("report-theme.json", "w"), indent=1)
diagram.theme = Theme.from_dict(json.load(open("report-theme.json")))
```

`Theme.from_dict` rejects unknown keys, so a misspelt option in a saved
theme is reported instead of silently ignored.

## The saturation curve

The `default` and `dark` themes draw the saturation curve heavier than
the isolines, in ink, with a casing: a band in the background colour on
both sides that keeps it apart from the lines crossing it. Where that
band does not look good, for example on a crowded chart or one printed
small, draw the curve without it:

```python
diagram.set_line_style("saturation", casing_width_pt=0)          # this chart only
diagram.set_line_style("saturation", casing_width_pt=0, width_pt=1.0, color="#52514e")
diagram.set_line_style("Q", color="#7a3cc8")                     # the lines of constant quality
diagram.set_line_style("saturation")                             # back to the theme

# In a theme of your own, for every chart drawn with it
mine = DEFAULT.with_(saturation=DEFAULT.saturation.with_(casing_width_pt=0))
```

`"saturation"` names the saturation curve (quality 0 and 1 of a fluid,
100 % relative humidity of air); `"Q"` (or `"RH"` on a psychrometric
chart) the lines inside the dome. The cycles have a casing too; they take
`line_style=` in `add_cycle`. A coolplot-core older than 1.3 cannot
restyle the curve; the Python composer then draws the chart, with a
warning.

## Style values

The style classes live in `coolplot.style`. They cannot be changed in
place; derive a changed copy with `.with_(...)`.

| Class | Fields |
|-------|--------|
| `LineStyle` | `color`, `width_pt`, `dash`, `alpha`, `cap` (butt, round, square), `join` (miter, round, bevel), `casing_color`, `casing_width_pt` |
| `MarkerStyle` | `shape` (o, s, ^, v, D, x, +), `size_pt`, `face_color` (None = hollow), `edge_color`, `edge_width_pt`, `alpha` |
| `Font` | `family` (list, first available wins), `size_pt`, `weight` (normal, bold), `style` (normal, italic), `files` (font files to load first) |
| `TextStyle` | `font`, `color`, `alpha`, `h_align`, `v_align`, `halo_color`, `halo_width_pt` |
| `AxesStyle` | `background`, `figure_background`, `frame_color`, `frame_width_pt`, tick colour, length, width and direction, fonts for `tick_label`, `axis_label` and `title`, `grid_major`, `grid_minor`, `legend` |
| `LegendStyle` | `visible`, `location` (upper/lower left/right, outside right, or "auto": inside, in the emptiest corner, the default since 1.2), `background`, `frame_color`, `text` |

Rules that hold everywhere:

* **Colours** are CSS colour names or hex codes (`#rgb`, `#rgba`,
  `#rrggbb`, `#rrggbbaa`); `"none"` means no paint. A typo fails at once,
  not later in one backend.
* **Transparency** belongs to the `alpha` fields. An alpha written into a
  `color` field ("#ff000080") is multiplied into that style's `alpha`.
  Colour fields without an alpha of their own (backgrounds, frame, ticks,
  marker edges and faces, casing, halo, palette) take only opaque colours;
  a fully transparent one means no paint.
* **Lengths** are typographic points (1/72 inch): line widths, marker
  sizes, font sizes, dash lengths, casing and halo widths.
* **Dashes** are `"solid"`, `"dashed"`, `"dotted"`, `"dashdot"`, or a
  tuple of on/off lengths in points. Named dashes scale with the line
  width but never below that of a 1 pt line, so thin isolines still show
  their pattern.
* **Casing** draws a band of `casing_color` on both sides of a line,
  underneath it, to lift the dome or a cycle off the lines it crosses.
* **Halo** is the same idea for text: an outline behind the glyphs keeps
  labels readable where they sit on lines.
* **Fonts** are lists: the first family that is installed wins, so end a
  list with "sans-serif", "serif" or "monospace". `files` names font
  files (.ttf preferred) that matplotlib registers first, for a company
  font that is not installed everywhere. Texts are plain text: dollar
  signs and backslashes are shown as written, never read as math.

## Legend

The first line of each family, the saturation dome, the quality lines
and each cycle carry a legend text. The legend sits outside the plot on
the right by default, so it never covers data; `LegendStyle(location=...)`
moves it and `LegendStyle(visible=False)` hides it.

## In the gallery

The same chart in the four themes: {doc}`../gallery/themes`. The
`coolpack` theme on the R290 chart of the CoolPack tutorial:
{doc}`../gallery/coolpack`.
