# Why the colours are what they are

Isolines of different families cross each other everywhere, so every
pair of family colours has to stay distinguishable: for readers with a
colour vision deficiency, in a black and white print, and on a
washed-out projector. Hue alone cannot do that, because hue is exactly
what those take away. The default colours therefore differ in hue and
also step in lightness: on the light surface the blue is dark, the red
middle and the teal light, so the three stay apart even as three greys.
Each reaches at least 3:1 contrast against the background, which WCAG
2.2 asks of lines that carry meaning. Three colours is about the most
that pass all of this together; fortunately every diagram type offers
exactly three coloured isoline families (plus quality, drawn in ink, and
the rarely used internal energy).

| Slot | Light | Dark | Families that land here |
|------|-------|------|-------------------------|
| 1 | `#c72500` red | `#ee7a5a` coral | T wherever offered; p in Ts, Trho; h in pT |
| 2 | `#2d03cd` blue | `#3a66d0` blue | s in ph, pT; p in hs; h in Ts, ps, prho, Trho |
| 3 | `#0ba589` teal | `#7ee6d2` aqua | rho wherever offered; s in prho, Trho |
| 4 | `#2d004b` aubergine | `#ffff78` pale lemon | u, only if requested |

The closest pair of the first three, as a distance in OKLab x100 (below
about 10, two thin lines are hard to tell apart):

| Surface | Normal vision | Deuteranopia | Protanopia | Tritanopia | Greyscale |
|---------|---------------|--------------|------------|------------|-----------|
| light | 32.3 | 15.0 | 27.6 | 25.2 | 14.6 |
| dark | 28.4 | 18.5 | 24.9 | 28.1 | 15.8 |

The dark theme steps the lightness the other way round (blue dark, coral
middle, aqua light), since on a dark surface the light colours stand
out. The {doc}`theme_catalog` shows these numbers for every theme,
computed when the documentation is built, and {doc}`accessibility` how
the colours were found and what they replaced.

The families a diagram offers, in the fixed order T, p, h, s, rho, u,
take the slots in turn. The consequences:

* temperature is always red and density always teal;
* on a T-s chart, where T and s are the axes, the isobars take the red,
  the isenthalps the blue and the isochores the teal;
* hiding a family never repaints the others, because the assignment
  depends on what the diagram offers, not on what is shown;
* the fourth slot (u) stays apart from the others (14.6 on the light
  surface, 10.9 on the dark one) but is close to the ink of the dome;
  isolines of u should carry labels if they are shown with three other
  families.

A colour per quantity instead, so that pressure had one colour on every
chart, would need six colours that stay apart in every pairing; three is
the most that pass. To pin a colour to a quantity regardless of the
diagram anyway, use `theme.with_isoline_color("p", "#7a3cc8")`; the
`classic` and `coolpack` themes do this for every family.

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
