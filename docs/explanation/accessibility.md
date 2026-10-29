# Colour and accessibility

A chart is only useful to readers who can read it. This page sets out
the rules CoolPlot's themes are measured against, who they are for, how
the themes do today, and a proposal for a better default. The numbers
for every theme are in the {doc}`theme_catalog`.

## The rules

CoolPlot aims at **WCAG 2.2, level AA**, the rule set behind the
European standard EN 301 549 (version 4.1.1, 2026) used under the
European Accessibility Act. It also covers the older WCAG versions that
US law refers to (2.1 for public universities under ADA Title II, 2.0
for Section 508). WCAG 3.0 is still a working draft without a contrast
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

## How the default does today

The default keeps the three families apart for red-green deficiencies
(worst pair 10.1), but three things fall short. The aqua isochores reach
only 2.7:1 contrast. In greyscale, entropy and density become the same
grey (3.3). And unless value labels are switched on, colour is the only
cue that tells the families apart, which WCAG 1.4.1 does not allow. The
dark theme gives all three families the same lightness, so it is weaker
still in greyscale (1.7) and for tritanopia (2.6).

## A better default: the proposal

Keeping the hues but putting them on a ladder of lightness fixes the
first two points. The proposal, not yet the default:

| Family on a log(p)-h chart | On a T-s chart | Colour | Contrast |
|---------------------------|----------------|--------|----------|
| T, isotherms | p, isobars | `#983e04` burnt orange | 6.8 |
| s, isentropes | h, isenthalps | `#040b8d` navy | 14.2 |
| rho, isochores | rho, isochores | `#2ba18f` teal | 3.1 |

The colours were found by searching the OKLCH colour space near the
default's hues for three colours that each reach 3:1 and whose closest
pair stays as far apart as possible for every simulated deficiency and in
greyscale. The closest pair improves from 10.1 to 19.3 for deuteranopia
and from 3.3 to 18.6 in greyscale. Temperature takes the warm colour, as
most readers expect.

:::{container} cp-pair
![The current default on a log(p)-h chart](../_generated/themes/default_ph.svg)
![The proposed default on a log(p)-h chart](../_generated/themes/candidate_ph.svg)
:::

The same two charts as a reader with deuteranopia sees them, and in
greyscale. In the current default (left) the isochores fade and, in
greyscale, take the grey of the isentropes; the proposal keeps three
steps of grey.

:::{container} cp-pair
![The current default as seen with deuteranopia](../_generated/themes/default_ph_deutan.svg)
![The proposed default as seen with deuteranopia](../_generated/themes/candidate_ph_deutan.svg)
:::

:::{container} cp-pair
![The current default in greyscale](../_generated/themes/default_ph_grey.svg)
![The proposed default in greyscale](../_generated/themes/candidate_ph_grey.svg)
:::

![Isoline colours of the proposed default under five kinds of colour vision](../_generated/themes/candidate_swatches.svg)

```{include} ../_generated/themes/candidate_scores.md
```

### And the T-s chart?

The T-s chart uses the same three colours, by position. Its isoline
families are p, h and rho (T and s are the axes), and in the fixed order
T, p, h, s, rho the isobars come first and take the orange, the
isenthalps the navy, the isochores the teal:

![The proposed default on a T-s chart](../_generated/themes/candidate_Ts.svg)

Giving every quantity a colour of its own instead, so that pressure had
the same colour on every chart, would need six colours (T, p, h, s, rho,
u) that stay apart in every pairing. Three is the most that pass the
tests above with enough contrast, so a fixed colour per quantity would
make every chart worse for readers with a colour vision deficiency. The
rules that hold instead: temperature is always the warm colour when it is
an isoline, density always teal, and hiding a family never repaints the
others. A user who prefers a colour per quantity can pin one with
`theme.with_isoline_color("p", ...)`, as the `classic` theme does.

The proposal still needs a look on real charts, on a projector and in
print, by readers with colour vision deficiencies, before it replaces the
default; the dark theme needs the same work.

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
