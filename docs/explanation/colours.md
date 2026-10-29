# Why the colours are what they are

Isolines of different families cross each other everywhere, so every
pair of family colours has to stay distinguishable, including for
readers with a colour vision deficiency. Of the eight hues in the
default palette only three pass that test for all pairs (worst pair in
OKLab x100 on the light surface: 10.1 for deuteranopia, 13.5 for
protanopia, 10.4 for tritanopia, 24.0 for normal vision). Every diagram
type offers exactly three coloured isoline families (plus quality, drawn
in ink, and the rarely used internal energy), so three are enough. On
the dark surface the stepped hues give 10.1 for deuteranopia, 13.6 for
protanopia and 20.9 for normal vision. Tritanopia, which is very rare,
separates blue and aqua poorly in the dark theme (2.6); labels or the
dash-based `print` theme cover that case. The {doc}`theme_catalog` shows
these numbers for every theme, computed when the documentation is built,
and {doc}`accessibility` what they miss and how the default could do
better.

| Slot | Light | Dark | Families that land here |
|------|-------|------|-------------------------|
| 1 | `#2a78d6` blue | `#3987e5` | T wherever offered; p in Ts, Trho; h in pT |
| 2 | `#eb6834` orange | `#d95926` | s in ph, pT; p in hs; h in Ts, ps, prho, Trho |
| 3 | `#1baf7a` aqua | `#199e70` | rho wherever offered; s in prho, Trho |
| 4 | `#eda100` yellow | `#c98500` | u, only if requested |

The families a diagram offers, in the fixed order T, p, h, s, rho, u,
take the slots in turn. The consequences:

* temperature is always blue and density always aqua;
* hiding a family never repaints the others, because the assignment
  depends on what the diagram offers, not on what is shown;
* the fourth slot (u) does not pass the all-pairs test against the
  others; isolines of u should carry labels if they are shown with three
  other families.

The light aqua and yellow have less than 3:1 contrast against the light
surface. Where those families matter, switch on value labels, which then
carry the information. To pin a colour to a quantity regardless of the
diagram, use `theme.with_isoline_color("T", "#c00000")`; the `classic`
and `coolpack` themes do this for every family.

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
