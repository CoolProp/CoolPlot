# -*- coding: utf-8 -*-
"""Pictures and numbers of the theme catalog, generated when the documentation is built.

Written by conf.py into _generated/themes, so that the pictures and the
contrast and separation numbers in explanation/theme_catalog.md and
explanation/accessibility.md always show the themes as the package has
them. For every theme it writes:

* ``<name>_ph.svg`` and ``<name>_Ts.svg``: a log(p)-h and a T-s chart of
  R290 with a cycle;
* ``<name>_swatches.svg``: the isoline colours as seen with normal colour
  vision, the three kinds of dichromacy and in greyscale;
* ``<name>_scores.md``: contrast and separation numbers as tables.

How colours are compared
------------------------
* Contrast is the WCAG 2.2 contrast ratio against the plot background.
  WCAG asks 3:1 for lines that carry meaning and 4.5:1 for text.
* Separation is the distance of two colours in OKLab (Ottosson 2020), a
  colour space where equal distances look about equally different,
  multiplied by 100. Below about 10 two thin lines are hard to tell apart.
* Colour vision deficiencies are simulated as recommended by DaltonLens:
  Vienot, Brettel and Mollon 1999 for protanopia and deuteranopia, Brettel,
  Vienot and Mollon 1997 for tritanopia. The coefficients are those of
  libDaltonLens (public domain), for linear sRGB.
* Greyscale keeps only the luminance, as in a black and white print or for
  readers with achromatopsia.
"""
import itertools
import os

#: The simulations, in the order of the columns of every picture and table.
SIMULATIONS = ("normal", "deutan", "protan", "tritan", "grey")
SIMULATION_NAMES = {"normal": "Normal vision", "deutan": "Deuteranopia", "protan": "Protanopia",
                    "tritan": "Tritanopia", "grey": "Greyscale"}

# Vienot 1999: one matrix from linear sRGB to the simulated linear sRGB
_VIENOT = {
    "protan": ((0.11238, 0.88762, 0.0), (0.11238, 0.88762, 0.0), (0.00401, -0.00401, 1.0)),
    "deutan": ((0.29275, 0.70725, 0.0), (0.29275, 0.70725, 0.0), (-0.02234, 0.02234, 1.0)),
}
# Brettel 1997 for tritanopia: two matrices, one for each side of a plane
# through the neutral axis, chosen by the sign of the dot product with its normal
_BRETTEL_TRITAN = (
    ((1.01277, 0.13548, -0.14826), (-0.01243, 0.86812, 0.14431), (0.07589, 0.80500, 0.11911)),
    ((0.93678, 0.18979, -0.12657), (0.06154, 0.81526, 0.12320), (-0.37562, 1.12767, 0.24796)),
    (0.03901, -0.02788, -0.01113),
)
# Relative luminance of linear sRGB (WCAG, ITU-R BT.709)
_LUMINANCE = (0.2126, 0.7152, 0.0722)

#: The colours of the default theme up to 1.4 (blue, orange, aqua, yellow),
#: for the comparison in explanation/accessibility.md.
PREVIOUS_DEFAULT_COLORS = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100")


# ---------------------------------------------------------------------------
# Colour arithmetic
# ---------------------------------------------------------------------------
def _hex_to_rgb(color):
    """'#rrggbb' to sRGB components between 0 and 1."""
    return tuple(int(color[i:i + 2], 16) / 255.0 for i in (1, 3, 5))


def _rgb_to_hex(rgb):
    return "#" + "".join("{0:02x}".format(int(round(255.0 * min(max(c, 0.0), 1.0)))) for c in rgb)


def _to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _to_srgb(c):
    c = min(max(c, 0.0), 1.0)
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1.0 / 2.4) - 0.055


def _times(matrix, vector):
    return tuple(sum(m * v for m, v in zip(row, vector)) for row in matrix)


def _simulate_linear(rgb, kind):
    """Linear sRGB as seen with the colour vision of ``kind``."""
    if kind == "normal":
        return rgb
    if kind == "grey":
        y = sum(w * c for w, c in zip(_LUMINANCE, rgb))
        return (y, y, y)
    if kind == "tritan":
        first, second, normal = _BRETTEL_TRITAN
        side = sum(n * c for n, c in zip(normal, rgb))
        return _times(first if side >= 0 else second, rgb)
    return _times(_VIENOT[kind], rgb)


def simulate(color, kind):
    """The colour '#rrggbb' as seen with the colour vision ``kind``, as '#rrggbb'."""
    linear = tuple(_to_linear(c) for c in _hex_to_rgb(color))
    return _rgb_to_hex(_to_srgb(c) for c in _simulate_linear(linear, kind))


def _oklab(color):
    """OKLab coordinates (L, a, b) of '#rrggbb'."""
    r, g, b = (_to_linear(c) for c in _hex_to_rgb(color))
    lms = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b,
           0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b,
           0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    l, m, s = (v ** (1.0 / 3.0) for v in lms)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def separation(color_a, color_b, kind="normal"):
    """Distance of two colours in OKLab x 100, as seen with the colour vision ``kind``."""
    a, b = _oklab(simulate(color_a, kind)), _oklab(simulate(color_b, kind))
    return 100.0 * sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def contrast(color_a, color_b):
    """WCAG 2.2 contrast ratio of two colours, from 1 to 21."""
    lum = sorted((sum(w * _to_linear(c) for w, c in zip(_LUMINANCE, _hex_to_rgb(x)))
                  for x in (color_a, color_b)), reverse=True)
    return (lum[0] + 0.05) / (lum[1] + 0.05)


# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------
def _is_hex(value):
    return isinstance(value, str) and len(value) == 7 and value.startswith("#")


def _map_colors(data, function):
    """A copy of a theme record with ``function`` applied to every colour in it."""
    if isinstance(data, dict):
        return {k: _map_colors(v, function) for k, v in data.items()}
    if isinstance(data, list):
        return [_map_colors(v, function) for v in data]
    return function(data) if _is_hex(data) else data


def simulated_theme(theme, kind):
    """The theme with every colour replaced by how it looks with the colour vision ``kind``.

    Drawing a chart with it shows the chart as such a reader sees it, as a
    vector picture.
    """
    from coolplot.style.theme import Theme
    record = _map_colors(theme.to_dict(), lambda c: simulate(c, kind))
    record["name"] = "{0}-{1}".format(theme.name, kind)
    return Theme.from_dict(record)


def previous_default_theme():
    """The default theme with the colours it had up to 1.4, as a Theme."""
    from coolplot.style.theme import DEFAULT
    return DEFAULT.with_(name="previous", categorical=PREVIOUS_DEFAULT_COLORS, isoline_colors=None)


def isoline_colors(theme, chart):
    """[(family, colour)] of the coloured isoline families of a chart type."""
    from coolplot.core.diagram_type import DiagramType
    families = [k for k in DiagramType.parse(chart).supported_isolines() if k not in ("Q", "u")]
    return [(k, theme.isoline_style(k, families).color) for k in families]


def _background(theme):
    return theme.axes.background or "#ffffff"


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def _color_rows(theme):
    """[(colour, 'T on ph, p on Ts')] for the isoline colours of a log(p)-h and a T-s chart."""
    rows = {}
    for chart in ("ph", "Ts"):
        for key, color in isoline_colors(theme, chart):
            rows.setdefault(color, []).append("{0} on {1}".format(key, chart))
    return [(color, ", ".join(uses)) for color, uses in rows.items()]


def swatches_svg(theme):
    """An SVG table: one row per isoline colour, one column per simulation."""
    rows = _color_rows(theme)
    label_w, cell_w, row_h, head_h = 150, 120, 26, 30
    width, height = label_w + cell_w * len(SIMULATIONS), head_h + row_h * len(rows) + 8
    background = _background(theme)
    ink = "#ffffff" if contrast(background, "#000000") < 7.0 else "#000000"
    width_px = max(theme.isoline.width_pt, 0.75) * 4.0 / 3.0   # the theme's own line width, at least 1 px
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="{0}" height="{1}" viewBox="0 0 {0} {1}" '
           'role="img" aria-labelledby="t">'.format(width, height),
           '<title id="t">Isoline colours of the theme {0}, as seen with normal colour vision, '
           'deuteranopia, protanopia, tritanopia and in greyscale</title>'.format(theme.name),
           '<rect width="100%" height="100%" fill="{0}"/>'.format(background),
           '<g font-family="Inter, Helvetica Neue, Arial, DejaVu Sans, sans-serif" font-size="12" fill="{0}">'.format(ink)]
    for i, kind in enumerate(SIMULATIONS):
        out.append('<text x="{0}" y="19" text-anchor="middle" font-weight="bold">{1}</text>'.format(
            label_w + cell_w * (i + 0.5), SIMULATION_NAMES[kind]))
    for j, (color, uses) in enumerate(rows):
        y = head_h + row_h * j + row_h / 2.0
        out.append('<text x="8" y="{0}" dominant-baseline="middle">{1}</text>'.format(y, uses))
        for i, kind in enumerate(SIMULATIONS):
            x0, shown = label_w + cell_w * i + 12, simulate(color, kind)
            # A bar to see the colour, and a line as thin as the isolines to see what is left of it
            out.append('<rect x="{0}" y="{1}" width="40" height="12" fill="{2}"/>'.format(x0, y - 6, shown))
            out.append('<line x1="{0}" y1="{1}" x2="{2}" y2="{1}" stroke="{3}" stroke-width="{4:.2f}"/>'.format(
                x0 + 48, y, x0 + cell_w - 20, shown, width_px))
    out.append("</g></svg>")
    return "\n".join(out) + "\n"


def _number(value, limit=None):
    text = "{0:.1f}".format(value)
    return "**{0}**".format(text) if limit is not None and value < limit else text


def scores_md(theme):
    """Markdown tables: contrast of every isoline colour, worst separation per chart and simulation."""
    background = _background(theme)
    out = ["| Isoline colour | Used for | Contrast on {0} |".format(background), "| --- | --- | --- |"]
    for color, uses in _color_rows(theme):
        out.append("| `{0}` | {1} | {2} |".format(color, uses, _number(contrast(color, background), 3.0)))
    if len(_color_rows(theme)) == 1:
        # One colour for every family (the print theme): the dash pattern tells them apart
        from coolplot.core.diagram_type import DiagramType
        out += ["", "| Chart | Dash pattern per family |", "| --- | --- |"]
        for chart in ("ph", "Ts"):
            families = [k for k in DiagramType.parse(chart).supported_isolines() if k not in ("Q", "u")]
            out.append("| {0} chart | {1} |".format(chart, ", ".join(
                "{0} {1}".format(k, theme.isoline_style(k, families).dash) for k in families)))
    else:
        out += ["", "| Worst pair | " + " | ".join(SIMULATION_NAMES[k] for k in SIMULATIONS) + " |",
                "| --- |" + " --- |" * len(SIMULATIONS)]
    for chart in ("ph", "Ts") if len(_color_rows(theme)) > 1 else ():
        colors = isoline_colors(theme, chart)
        cells = []
        for kind in SIMULATIONS:
            value, a, b = min((separation(ca, cb, kind), ka, kb)
                              for (ka, ca), (kb, cb) in itertools.combinations(colors, 2))
            cells.append("{0} ({1}, {2})".format(_number(value, 10.0), a, b))
        out.append("| {0} chart | ".format(chart) + " | ".join(cells) + " |")
    label = theme.isoline_label
    if theme.isoline_label_color == "line":
        text = ", ".join("{0:.1f}".format(contrast(c, background)) for c, _ in _color_rows(theme))
        out += ["", "Isoline labels take the colour of their line: text contrast {0} (WCAG asks 4.5).".format(text)]
    elif label.color:
        out += ["", "Isoline labels: `{0}`, text contrast {1:.1f} (WCAG asks 4.5).".format(
            label.color, contrast(label.color, background))]
    out += ["", "Bold: contrast below 3:1, or separation below 10."]
    return "\n".join(out) + "\n"


def _diagrams():
    """A log(p)-h and a T-s chart of R290 with a heat pump cycle, labels on."""
    from coolplot import PropertyDiagram
    from coolplot.thermo.cycles import simple_compression
    charts = {}
    for chart, families in (("ph", ("T", "s", "rho")), ("Ts", ("p", "h", "rho"))):
        d = PropertyDiagram("HEOS::R290", chart, units="engineering", tp_limits="ACHP")
        d.set_lines("Q", num=11)
        for key, num in zip(families, (8, 7, 6)):
            d.set_lines(key, num=num, rounding=True, labels=True)
        d.add_cycle(simple_compression(d.fluid, T_evap_C=-5.0, T_cond_C=45.0))
        charts[chart] = d
    return charts


def _draw(diagram, theme, title, path, width=560, height=400):
    from coolplot.render.svg import SvgRenderer
    diagram.theme = theme
    diagram.title = title
    diagram.draw(SvgRenderer(width=width, height=height)).save(path)


def write(folder):
    """Write every picture and table of the catalog into ``folder``."""
    from coolplot.style.theme import DEFAULT, THEMES
    os.makedirs(folder, exist_ok=True)
    charts = _diagrams()
    themes = dict(THEMES)
    themes["previous"] = previous_default_theme()
    titles = {name: 'R290, theme="{0}"'.format(name) for name in THEMES}
    titles["previous"] = "R290, default up to 1.4"
    for name, theme in themes.items():
        for chart, diagram in charts.items():
            _draw(diagram, theme, titles[name], os.path.join(folder, "{0}_{1}.svg".format(name, chart)))
        with open(os.path.join(folder, name + "_swatches.svg"), "w") as f:
            f.write(swatches_svg(theme))
        with open(os.path.join(folder, name + "_scores.md"), "w") as f:
            f.write(scores_md(theme))
    # The default up to 1.4 and now, as readers with deuteranopia and in greyscale see them
    for theme, title in ((themes["previous"], "Default up to 1.4"), (DEFAULT, "Default")):
        for kind in ("deutan", "grey"):
            _draw(charts["ph"], simulated_theme(theme, kind), "{0}, {1}".format(title, SIMULATION_NAMES[kind].lower()),
                  os.path.join(folder, "{0}_ph_{1}.svg".format(theme.name, kind)))
