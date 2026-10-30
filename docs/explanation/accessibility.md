# Colour and accessibility

A chart is only useful to readers who can read it. This page sets out
the rules CoolPlot's themes are measured against, who they are for, and
how the colours of the default theme were chosen. The numbers for every
theme are in the {doc}`theme_catalog`.

## The rules

CoolPlot aims at **WCAG 2.2, level AA**. It is the rule set of version
4.1.1 of the European standard EN 301 549 (published in 2026); until the
European Commission cites that version, version 3.2.1 (WCAG 2.1) remains
the reference under the European Accessibility Act. WCAG 2.2 AA also
covers the older WCAG versions that law refers to: 2.1 for EN 301 549
3.2.1 and for public universities under the US ADA Title II, 2.0 for
Section 508. WCAG 3.0 is still a working draft without a contrast
formula, so APCA, the contrast method discussed for it, is at most an
extra check.

For a chart, WCAG 2.2 asks four things:

| Criterion | What it means for a property chart |
|-----------|-----------------------------------|
| 1.1.1 Non-text content | A text alternative; a data table next to the chart also counts. |
| 1.4.1 Use of colour | Colour must not be the only way to tell isotherms from isentropes. Value labels or dash patterns are the second cue. |
| 1.4.11 Non-text contrast | Every line that carries meaning reaches 3:1 against the background. Lines need not contrast with each other or with the grid. |
| 1.4.3 Contrast | Text, including the small isoline labels, reaches 4.5:1 against what is behind it; the halo takes care of the lines it crosses. |

The scientific literature adds three rules that WCAG does not spell out:

* **Vary lightness, not only hue** (Wong 2011, Crameri et al. 2020). Two
  colours of equal lightness differ only in hue, and hue is exactly what
  a colour vision deficiency, a greyscale print or a washed-out
  projector takes away.
* **No red with green at similar lightness** (Crameri et al. 2020).
* **Use line types as well as colours** where lines must be told apart
  (Tol). The `print` theme does this; a theme with colour can do it too.

No published source gives a minimum colour difference for thin lines,
and none sets a colour convention for isotherms or isentropes (IIR,
ASHRAE, DIN and ISO are silent). CoolPlot uses a distance of 10 in OKLab
x100 as the line below which two families count as hard to tell apart.

## Who the themes are for

| Readers | How many | What helps them | Theme |
|---------|----------|-----------------|-------|
| Red-green colour vision deficiency | about 8 % of men and 0.4 % of women of European descent | colour pairs that also differ in blue-yellow and in lightness | the default, for everybody |
| Tritanopia (blue-yellow) | very rare | colours that differ in lightness | the default, by its lightness |
| No colour vision, greyscale print | about 1 in 30,000 people, and every photocopy | dash patterns, or clear steps in lightness | `print` |
| Low vision, projectors in lit rooms | the largest group | high contrast, thicker lines, larger text (`Settings.page.font_scale`) | a high contrast theme, proposed below |
| Blind readers | | a text alternative and the data as a table | output features, not a theme |
| Dyslexia | | a clear sans-serif at a readable size; there is no evidence that special fonts help | the default fonts |

Colour vision deficiencies belong in the default, not in an option: one
in twelve male readers should not have to look for a setting. Most of
them are anomalous trichromats, who see colours shifted rather than
missing; a palette that works for full dichromats works for them too.

## How the default colours were chosen

Up to 1.4 the default drew isotherms blue, isentropes orange and
isochores aqua. Those kept the families apart for red-green deficiencies
(closest pair 10.1 in OKLab x100), but fell short in three ways: the aqua
reached only 2.7:1 contrast, entropy and density turned into the same grey
in a black and white print (3.3), and the dark theme gave all three
colours the same lightness (1.7 in greyscale, 2.6 for tritanopia).

Since 1.5 every quantity has a colour of its own, the same on every
chart. They were found in two steps, both by a search in the OKLCH colour
space among colours with at least 3:1 contrast on the background:

1. Red for temperature, blue for entropy and teal for density, the
   colours most engineers expect, for the log(p)-h chart: within a window
   of hue around each, the three whose closest pair stays furthest apart
   for deuteranopia, protanopia, tritanopia and in greyscale. The answer
   steps in lightness: on the light surface the blue is dark, the red
   middle and the teal light.
2. Pressure and enthalpy, around those three: every pair of T, p, h, s
   and rho meets on some chart type (and, with horizontal and vertical
   isolines, on one chart), so the two were searched over all hues for
   the largest closest pair of all ten, for normal vision and the three
   deficiencies. Internal energy, rarely drawn, came last.

| Quantity | Light theme | Contrast | Dark theme | Contrast |
|----------|-------------|----------|------------|----------|
| T, isotherms | `#c72500` red | 5.5 | `#ee7a5a` coral | 6.3 |
| p, isobars | `#621b40` wine | 11.7 | `#9a9ad8` periwinkle | 6.6 |
| h, isenthalps | `#ce52f9` orchid | 3.3 | `#9f4e64` dusky rose | 3.1 |
| s, isentropes | `#2d03cd` blue | 10.2 | `#3a66d0` blue | 3.3 |
| rho, isochores | `#0ba589` teal | 3.0 | `#7ee6d2` aqua | 11.7 |
| u | `#87459f` purple | 6.0 | `#f6c919` yellow | 11.0 |

The closest of the ten pairs stays at 15.0 for deuteranopia on the light
surface (16.8 on the dark one), as far apart as red, blue and teal alone.
What five colours cannot do is stay five greys: on a T-s chart printed
in black and white, enthalpy and density look alike, so print in the
`print` theme or with value labels.

On the log(p)-h chart the closest pair improves from 10.1 to 15.0 for
deuteranopia and from 3.3 to 14.6 in greyscale on the light surface, and
from 1.7 to 15.8 in greyscale on the dark one. A deeper navy instead of
the blue would give about 19, but reads as navy, not blue.

:::{container} cp-pair
![The default theme up to 1.4 on a log(p)-h chart](../_generated/themes/previous_ph.svg)
![The default theme on a log(p)-h chart](../_generated/themes/default_ph.svg)
:::

The same two charts as a reader with deuteranopia sees them, and in
greyscale. With the colours up to 1.4 (left) the isochores fade and, in
greyscale, take the grey of the isentropes; the current default keeps
three steps of grey.

:::{container} cp-pair
![The default up to 1.4 as seen with deuteranopia](../_generated/themes/previous_ph_deutan.svg)
![The default as seen with deuteranopia](../_generated/themes/default_ph_deutan.svg)
:::

:::{container} cp-pair
![The default up to 1.4 in greyscale](../_generated/themes/previous_ph_grey.svg)
![The default in greyscale](../_generated/themes/default_ph_grey.svg)
:::

### And the T-s chart?

The T-s chart keeps the colours of its quantities: its isoline families
are p, h and rho (T and s are the axes), drawn wine, orchid and teal.
Pressure is wine on every chart where it is an isoline, and so on for
every quantity:

![The default theme on a T-s chart](../_generated/themes/default_Ts.svg)

Up to 1.4, and in a theme without pinned colours (the `print` theme, or
one derived with `isoline_colors=None`), the colours went out by
position instead: the first family a chart offered took the first
colour. That needs only three colours, but the same colour then meant
pressure on one chart and temperature on another. To change the colour
of one quantity, use `theme.with_isoline_color("p", ...)`.

## More than colour

Proposed next steps, in order of how much they help:

* **A second cue by default**: value labels on, or the dash patterns of
  `print` added to the colour themes, so that colour is never the only
  cue.
* **A text alternative in the SVG**: `role="img"`, a `<title>` and a
  `<desc>` that names the fluid, the chart type, the families with their
  ranges and the states of the cycle, and the cycle states as a table
  (HTML and CSV) next to the chart.
* **A high contrast theme** for low vision and projectors: 7:1 for text
  and lines, isolines of 1 pt or more, a heavier dome, larger text, and
  colour and dash on every family.
* **The web page**: a `lang` attribute, keyboard control of the
  interactive chart, and styles for the browser settings
  `prefers-color-scheme`, `prefers-contrast` and `forced-colors` (where
  every line turns one colour and only dashes keep the families apart).
* **A check in the tests**: the numbers of the catalog for every theme
  that claims to be accessible, so that a change cannot quietly make one
  worse.

## Sources

* W3C, [Understanding 1.4.11 Non-text Contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html)
  and [Understanding 1.4.1 Use of Color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html)
* W3C, [WCAG 3.0 Working Draft](https://www.w3.org/TR/wcag-3.0/)
* Deque, [EN 301 549 v4.1.1 is final](https://www.deque.com/de/blog/en-301-549-v4-1-1-is-final-what-changed-what-it-means-and-what-you-should-do/)
* Crameri, Shephard and Heron (2020), [The misuse of colour in science communication](https://pmc.ncbi.nlm.nih.gov/articles/PMC7595127),
  Nature Communications 11, 5444
* Wong (2011), [Points of view: Color blindness](https://www.nature.com/articles/nmeth.1618), Nature Methods 8, 441
* Paul Tol, [Colour schemes and templates](https://sronpersonalpages.nl/~pault/)
* Szafir (2018), [Modeling color difference for visualization design](https://cmci.colorado.edu/visualab/VisColors/)
* Birch (2012), [Worldwide prevalence of red-green color deficiency](https://pubmed.ncbi.nlm.nih.gov/22472762/)
* DaltonLens, [Review of open source colour blindness simulations](https://daltonlens.org/opensource-cvd-simulation/)
  and [libDaltonLens](https://github.com/DaltonLens/libDaltonLens) (public domain), whose coefficients the catalog uses
* Ottosson (2020), [A perceptual color space for image processing](https://bottosson.github.io/posts/oklab/) (OKLab)
* Wery and Diliberto (2017), [The effect of a specialized dyslexia font, OpenDyslexic](https://link.springer.com/article/10.1007/s11881-016-0127-1)
* MDN, [forced-colors](https://developer.mozilla.org/docs/Web/CSS/@media/forced-colors)
