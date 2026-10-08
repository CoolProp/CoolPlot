# Styling property diagrams

Every visual property of a CoolPlot diagram comes from a **theme**. The
diagram resolves the theme into concrete styles when it builds the scene,
so a chart looks the same whether matplotlib, the SVG backend or a future
web backend draws it. Changing the theme never recalculates properties;
only the restyled items are redrawn.

```python
from CoolPlot import PropertyDiagram
diagram = PropertyDiagram("HEOS::R290", "ph", units="EUR", theme="default")
diagram.theme = "dark"                                 # switch at any time
diagram.set_isoline_style("T", width_pt=1.0)           # one family, this diagram only
```


## 1. Style values

All style classes live in `CoolPlot/style.py`. They are immutable; derive
a changed copy with `.with_(...)`.

| Class | Fields |
|-------|--------|
| `LineStyle` | `color`, `width_pt`, `dash`, `alpha`, `cap` (butt, round, square), `join` (miter, round, bevel), `casing_color`, `casing_width_pt` |
| `MarkerStyle` | `shape` (o, s, ^, v, D, x, +), `size_pt`, `face_color` (None = hollow), `edge_color`, `edge_width_pt`, `alpha` |
| `Font` | `family` (list, first available wins), `size_pt`, `weight` (normal, bold), `style` (normal, italic) |
| `TextStyle` | `font`, `color`, `alpha`, `h_align`, `v_align`, `halo_color`, `halo_width_pt` |
| `AxesStyle` | `background`, `figure_background`, `frame_color`, `frame_width_pt`, tick colour, length, width and direction, fonts for `tick_label`, `axis_label` and `title`, `grid_major`, `grid_minor`, `legend` |
| `LegendStyle` | `visible`, `location` (upper/lower left/right, outside right), `background`, `frame_color`, `text` |

Rules that hold everywhere:

* **Colours** are CSS colour names or hex codes (`#rgb`, `#rgba`,
  `#rrggbb`, `#rrggbbaa`); `"none"` means no paint. They are normalised to
  `#rrggbb` when the style is created, and an alpha inside the colour is
  multiplied into `alpha`. A typo fails immediately, not later in one
  backend.
* **Lengths** are typographic points (1/72 inch): line widths, marker
  sizes, font sizes, dash lengths, casing and halo widths.
* **Dashes** are `"solid"`, `"dashed"`, `"dotted"`, `"dashdot"`, or a tuple
  of on/off lengths in points. Named dashes scale with the line width but
  never below that of a 1 pt line, so thin isolines still show their
  pattern.
* **Casing** draws a band of `casing_color` on both sides of a line,
  underneath it. With the background colour it lifts an important line
  (the saturation dome, a cycle) off the isolines it crosses.
* **Halo** is the same idea for text: an outline in `halo_color` behind
  the glyphs keeps labels readable where they sit on lines, without
  hiding the lines behind a box.


## 2. Presets

| Theme | Use |
|-------|-----|
| `default` | Screen, light background. Colours checked for colour vision deficiencies. |
| `dark` | Screen, dark background. The same hues stepped and checked for the dark surface. |
| `print` | Black and white. Families differ by dash pattern only. |
| `classic` | The colours of the CoolProp plots before 2026, no legend, no grid. |

In `default` and `dark`, isolines are thin reference lines in colour. The
saturation dome and cycles are drawn in ink, heavier and with a casing, so
they read as the subject of the chart. Text always uses ink colours, never
a series colour. Quality lines inside the dome use a muted ink.


## 3. How isoline colours are assigned

Isolines of different families cross each other everywhere, so every pair
of family colours has to remain distinguishable, including for readers
with a colour vision deficiency. Of the eight hues in the default palette,
only three pass that test for all pairs (worst pair: CVD Delta E 9.2,
normal vision 24.0 in OKLab x100, light surface). Every diagram type offers
exactly three coloured isoline families (plus quality, drawn in ink, and
the rarely used internal energy), so three are enough:

| Slot | Light | Dark | Families that land here |
|------|-------|------|-------------------------|
| 1 | `#2a78d6` blue | `#3987e5` | T wherever offered; p in Ts, Trho; h in pT |
| 2 | `#eb6834` orange | `#d95926` | s in ph, pT; p in hs; h in Ts, ps, prho, Trho |
| 3 | `#1baf7a` aqua | `#199e70` | rho wherever offered; s in prho, Trho |
| 4 | `#eda100` yellow | `#c98500` | u, only if requested |

The families a diagram offers, in the fixed order T, p, h, s, rho, u, take
the slots in turn. The consequences:

* temperature is always blue and density always aqua;
* hiding a family never repaints the others, because the assignment
  depends on what the diagram *offers*, not on what is shown;
* the fourth slot (u) does not pass the all-pairs test against the others.
  Isolines of u should carry labels if they are shown with three other
  families.

The light aqua and yellow have less than 3:1 contrast against the light
surface. Where those families matter, switch on value labels
(`set_isolines(..., labels=True)`), which then carry the information.

To pin a colour to a quantity regardless of the diagram, use
`theme.with_isoline_color("T", "#c00000")`. The `classic` theme does this
for every family.


## 4. Customising

Three levels, from narrow to broad:

```python
# One family in one diagram, any LineStyle field
diagram.set_isoline_style("s", dash="dashed")
diagram.set_isoline_style("s")                          # back to the theme

# A derived theme
from CoolPlot.theme import DEFAULT
mine = DEFAULT.with_(name="report", isoline=DEFAULT.isoline.with_(width_pt=0.5))
mine = mine.with_isoline_color("T", "darkred")
diagram.theme = mine

# Saved and loaded as JSON
import json
json.dump(mine.to_dict(), open("report-theme.json", "w"), indent=1)
diagram.theme = Theme.from_dict(json.load(open("report-theme.json")))
```

`Theme.from_dict` rejects unknown keys, so a misspelt option in a saved
theme is reported instead of silently ignored.


## 5. Roles, groups and drawing order

Every scene item carries a semantic `role`, independent of its style:

| Role | Items | z order |
|------|-------|---------|
| `isoline` | lines of constant T, p, h, s, rho, u | 1 |
| `quality` | lines of constant quality inside the dome | 1 |
| `saturation` | bubble and dew lines | 2 |
| `isoline_label` | value labels | 4 |
| `process` | process and cycle lines | 5 |
| `state_points` | markers on process states | 6 |

Items with equal z order are drawn in the order the diagram added them.
Backends that support external styling (the SVG backend) expose roles and
groups as CSS classes such as `cp-role-isoline cp-group-iso-T`, so a web
page can restyle a chart with a stylesheet.


## 6. Legend

The first line of each isoline family, the saturation dome, the quality
lines and each process carry a legend text. Items that share a text form
one entry whose sample overlays them, so a cycle's entry shows its line
with a marker. The legend sits outside the plot on the right by default,
so it never covers data; `LegendStyle(location=...)` moves it and
`LegendStyle(visible=False)` hides it.
