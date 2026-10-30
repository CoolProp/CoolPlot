# Theme catalog

Every theme that comes with CoolPlot, drawn on the same two charts of
R290 (a log(p)-h and a T-s chart with a heat pump cycle), with the reasons
for its colours and the numbers that show how well they work. The
pictures and numbers are made from the package when this documentation is
built, so they always show the themes as they are.

How to read each entry:

* **The charts** show the theme as most readers see it.
* **The colour strip** shows each isoline colour as a bar and as a line
  as thin as the theme's isolines, the way it looks with normal colour
  vision, with the three kinds of dichromacy (one type of cone missing)
  and in greyscale (a black and white print, or achromatopsia). Two rows
  that look alike in a column are two families that reader cannot tell
  apart by colour.
* **The tables** give the contrast of each colour against the plot
  background (WCAG 2.2 asks 3:1 for lines that carry meaning) and, per
  chart, the pair of families whose colours are closest, as a distance in
  OKLab x100. Below about 10, two thin lines are hard to tell apart; bold
  marks values below 3:1 or 10.

The simulations follow the recommendation of DaltonLens: Vienot (1999)
for protanopia and deuteranopia, Brettel (1997) for tritanopia. How the
colours of a theme are given to the families of a chart is explained in
{doc}`colours`; what the themes miss, and how the default could do
better, in {doc}`accessibility`.

| Theme | Made for | Families told apart by |
|-------|----------|------------------------|
| `default` | screens with a light background, colour print | one colour per quantity, checked for colour vision deficiencies |
| `dark` | screens with a dark background | one colour per quantity, checked the same way |
| `print` | black and white print, photocopies | dash pattern only |
| `coolpack` | the look of CoolPack's charts, late 1990s | colour per quantity, and labels in line colour |

## default

The default is built for the screen and for colour print, and for the
roughly one in twelve men who see colours differently.

**Why these colours.** Every quantity has a colour of its own, the same
on every chart: red for temperature, wine for pressure, orchid for
enthalpy, blue for entropy, teal for density, purple for internal energy.
Red, blue and teal, the three families of the log(p)-h chart, also step
in lightness (blue dark, red middle, teal light), so that chart keeps
three greys even in a black and white print. Wine and orchid were chosen
to stay apart from all of them, since every pair of the five meets on
some chart type; each colour reaches at least 3:1 against the background,
as WCAG 2.2 asks of lines. The saturation dome and the cycles are drawn
in ink, heavier and with a band in the background colour along them (the
casing), so they read as the subject and the coloured isolines as the
reference behind them. Labels are dark grey ink (7.7:1), readable on
every line they cross. How the colours were found is in
{doc}`accessibility`.

**Weak points.** Five colours cannot also stay five greys: on a T-s chart
printed in black and white, enthalpy and density look alike (use the
`print` theme or value labels there). The teal is just at 3:1, too light
for text: labels in line colour (`isoline_label_color="line"`) are harder
to read for the isochores. Colour is the only cue between families unless
value labels are switched on.

:::{container} cp-pair
![The default theme on a log(p)-h chart](../_generated/themes/default_ph.svg)
![The default theme on a T-s chart](../_generated/themes/default_Ts.svg)
:::

![Isoline colours of the default theme under five kinds of colour vision](../_generated/themes/default_swatches.svg)

```{include} ../_generated/themes/default_scores.md
```

## dark

The default for a dark background, for dark mode screens and slides.

**Why these colours.** The same quantities on a near-black surface:
coral for temperature, periwinkle for pressure, dusky rose for enthalpy,
blue for entropy, aqua for density, yellow for internal energy, searched
for the dark surface in the same way. On a dark surface the light colours
stand out, so on the log(p)-h chart the lightness steps the other way
round (blue dark, coral middle, aqua light). Each reaches at least 3:1.
Ink becomes white, the casing dark.

**Weak points.** The blue and the dusky rose are just above 3:1 and the
dimmest; on a projector in a lit room the `default` theme reads better.

:::{container} cp-pair
![The dark theme on a log(p)-h chart](../_generated/themes/dark_ph.svg)
![The dark theme on a T-s chart](../_generated/themes/dark_Ts.svg)
:::

![Isoline colours of the dark theme under five kinds of colour vision](../_generated/themes/dark_swatches.svg)

```{include} ../_generated/themes/dark_scores.md
```

## print

For black and white printers, photocopies, and readers who see no
colour at all.

**Why these colours.** There is one: a dark grey (11.4:1) for every
isoline family, so nothing depends on colour. The families differ by
dash pattern instead: the first solid, the second dashed, the third
dotted. Named dash patterns grow with the line width, but never below
those of a 1 pt line, so that the 0.6 pt isolines still show their
pattern. The background is pure white for paper and the grid a light
grey that a printer still reproduces.

:::{container} cp-pair
![The print theme on a log(p)-h chart](../_generated/themes/print_ph.svg)
![The print theme on a T-s chart](../_generated/themes/print_Ts.svg)
:::

![Isoline colour of the print theme under five kinds of colour vision](../_generated/themes/print_swatches.svg)

```{include} ../_generated/themes/print_scores.md
```

## coolpack

The look of the log(p),h-diagrams of CoolPack, the refrigeration
programs of the Technical University of Denmark (DTU) from the late
1990s. CoolPack is DTU's program; the theme only imitates the look of its
charts and is not connected to DTU or the CoolPack authors.

**Why these colours.** They are copied from the R290 chart in the
CoolPack tutorial: red isotherms, blue isentropes, green isochores, navy
lines of constant quality and a black dome. All are colours of the 16
colour Windows palette, the colours a Windows program of the time could
count on every screen to show without dithering, which is why they are
pure and saturated. With no legend, each label takes the colour of its
line, so the families are told apart by their labels. Times on white with
a dense light grey grid completes the look. The tutorial shows no T-s
chart, so the purple isobars and magenta isenthalps were chosen from the
same palette to stay apart from the green isochores; they are not copied.
See it on a full chart in the gallery: {doc}`../gallery/coolpack`.

**Weak points.** Red and green, the best-known combination to avoid, are
hard to tell apart with protanopia. Red labels reach 4.0:1, below the
4.5:1 WCAG asks for text. The theme recreates a look and makes no promise
on accessibility.

:::{container} cp-pair
![The coolpack theme on a log(p)-h chart](../_generated/themes/coolpack_ph.svg)
![The coolpack theme on a T-s chart](../_generated/themes/coolpack_Ts.svg)
:::

![Isoline colours of the coolpack theme under five kinds of colour vision](../_generated/themes/coolpack_swatches.svg)

```{include} ../_generated/themes/coolpack_scores.md
```
