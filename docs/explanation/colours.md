# Why the colours are what they are

Isolines of different families cross each other everywhere, so every
pair of family colours has to stay distinguishable, including for
readers with a colour vision deficiency. The default themes give every
quantity a colour of its own, the same on every chart, so a reader who
has learned that temperature is red finds it red on a log(p)-h, a T-s or
an h-s chart alike:

| Quantity | Light | Dark |
|----------|-------|------|
| T, temperature | `#c72500` red | `#ee7a5a` coral |
| p, pressure | `#621b40` wine | `#9a9ad8` periwinkle |
| h, enthalpy | `#ce52f9` orchid | `#9f4e64` dusky rose |
| s, entropy | `#2d03cd` blue | `#3a66d0` blue |
| rho, density | `#0ba589` teal | `#7ee6d2` aqua |
| u, internal energy | `#87459f` purple | `#f6c919` yellow |
| T_wb, wet-bulb temperature | as entropy | as entropy |
| v, specific volume | as density | as density |

Every pair of T, p, h, s and rho meets on some chart type (with
horizontal and vertical isolines, on one chart), so all five have to
stay apart from each other. Red, blue and teal were chosen first, for the
log(p)-h chart, by a search for the three colours whose closest pair
stays furthest apart; wine and orchid were then searched to fit around
them. Each reaches at least 3:1 contrast against the background, which
WCAG 2.2 asks of lines that carry meaning. The closest pair of the five,
as a distance in OKLab x100 (below about 10, two thin lines are hard to
tell apart):

| Surface | Normal vision | Deuteranopia | Protanopia | Tritanopia | Greyscale |
|---------|---------------|--------------|------------|------------|-----------|
| light | 23.1 | 15.0 | 17.6 | 17.0 | 2.3 |
| dark | 19.4 | 16.8 | 17.1 | 17.0 | 1.4 |

Five colours cannot also stay apart as greys: on the light T-s chart,
enthalpy and density become nearly the same grey. For black and white
print, use the `print` theme, which tells the families apart by dash
pattern, or switch on value labels. On the log(p)-h chart, red, blue and
teal still keep three steps of grey (14.6 light, 15.8 dark). The
{doc}`theme_catalog` shows these numbers per chart for every theme,
computed when the documentation is built, and {doc}`accessibility` how
the colours were found and what they replaced.

Wet-bulb temperature takes the colour of entropy and specific volume
that of density, since neither entropy nor density appears on a
psychrometric chart.

A theme pins its colours with `isoline_colors`. A theme without them
(the `print` theme, or one derived with `isoline_colors=None`) gives out
the colours of `categorical` by position instead: the families a diagram
offers, in the fixed order T, p, h, s, rho, u, take the slots in turn, so
hiding a family never repaints the others. To change the colour of one
quantity, use `theme.with_isoline_color("p", "#7a3cc8")`.

## Ink and reference lines

In `default` and `dark`, isolines are thin reference lines in colour.
The saturation dome and the cycles are drawn in ink, heavier and with a
casing in the background colour, so they read as the subject of the
chart and stay visible where they cross the reference lines. Text uses
ink colours by default, not series colours, so a label is readable whatever
it sits on; a halo in the background colour keeps it readable on a line.
A theme with `isoline_label_color="line"` trades some of that contrast
for labels that match their family at a glance.

## Roles and drawing order

Every drawn item carries a role, independent of its style, and items
are drawn in the order of their roles:

| Role | Items | z order |
|------|-------|---------|
| `isoline` | lines of constant T, p, h, s, rho, u | 1 |
| `quality` | lines of constant quality inside the dome | 1 |
| `saturation` | bubble and dew lines | 2 |
| `isoline_label` | value labels | 4 |
| `process` | process and cycle lines | 5 |
| `state_points` | markers on process states | 6 |

Items of equal order are drawn in the order they were added. The SVG
writer exposes roles and groups as CSS classes such as
`cp-role-isoline cp-group-iso-T`, so a web page can restyle a chart with
a stylesheet.
