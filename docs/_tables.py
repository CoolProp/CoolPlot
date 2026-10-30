# -*- coding: utf-8 -*-
"""Reference tables generated from the code when the documentation is built.

Written by conf.py into reference/tables.md, so that the tables of
diagram types, line families, limit presets, unit systems, settings
presets and themes can never drift from what the package does.
"""
import io


def _row(*cells):
    return "| " + " | ".join(str(c) for c in cells) + " |\n"


def write(path):
    from coolplot.core.diagram_type import FAMILIES, DiagramType, _AXIS_NAMES
    from coolplot.core.limits import TP_LIMITS
    from coolplot.core.quantities import QUANTITIES, _ALIASES
    from coolplot.core.units import UNIT_SYSTEMS, BAR_GAUGE, PSI_GAUGE
    from coolplot.spec.settings import PRESETS
    from coolplot.style.theme import THEMES

    out = io.StringIO()
    out.write("# Tables\n\nGenerated from the package when the documentation is built.\n\n")

    out.write("## Quantities and aliases\n\n")
    out.write(_row("Key", "Quantity", "Symbol", "CoolProp name", "HAPropsSI name", "Log axis", "Aliases"))
    out.write(_row(*["---"] * 7))
    for q in QUANTITIES.values():
        aliases = ", ".join("`{0}`".format(a) for a, k in _ALIASES.items() if k == q.key)
        out.write(_row("`{0}`".format(q.key), q.label, q.symbol, q.coolprop_name or "", q.humid_air_name or "",
                       "yes" if q.log_scale else "", aliases))

    out.write("\n## Diagram types and line families\n\n")
    out.write("The vertical axis comes first in the name. A family is stepped in the quantity shown and "
              "leaves the chart at the edges listed, where its labels sit.\n\n")
    out.write(_row("Diagram", "Vertical", "Horizontal", "Families (stepped in; preferred label edges)"))
    out.write(_row(*["---"] * 4))
    for name in ("ph", "Ts", "hs", "ps", "prho", "Trho", "pT", "WT", "ThxW"):
        d = DiagramType.parse(name)
        families = "; ".join("{0} ({1}; {2})".format(f.key, f.sweep, ", ".join(f.edges)) for f in d.families)
        out.write(_row("`{0}`".format(name), d.quantity_label(d.y), d.quantity_label(d.x), families))
    out.write("\nFamilies by kind of chart: " + "; ".join(
        "{0}: {1}".format(kind, ", ".join(f.key for f in fams)) for kind, fams in FAMILIES.items()) + ".\n")
    if "humid_air" in _AXIS_NAMES:
        out.write("\nIn a psychrometric chart the axes are called " + ", ".join(
            "{0} ({1})".format(v, k) for k, v in _AXIS_NAMES["humid_air"].items()) + ".\n")

    out.write("\n## Limit presets (`tp_limits`)\n\n")
    out.write("Relative bounds are factors of the saturation range (triple point to critical point) of "
              "the fluid; absolute ones are in K and Pa; None is the limit of the equation of state.\n\n")
    out.write(_row("Name", "T_min", "T_max", "p_min", "p_max"))
    out.write(_row(*["---"] * 5))
    def bound(value):
        factor = getattr(value, "factor", None)
        return "{0:g} x saturation".format(factor) if factor is not None else ("None" if value is None else value)
    for name, limits in TP_LIMITS.items():
        out.write(_row("`{0}`".format(name), *[bound(v) for v in (limits.T_min, limits.T_max, limits.p_min,
                                                                   limits.p_max)]))

    out.write("\n## Unit systems\n\n")
    keys = list(QUANTITIES)
    out.write(_row("System", *keys))
    out.write(_row(*["---"] * (len(keys) + 1)))
    for system in UNIT_SYSTEMS.values():
        out.write(_row(system.name, *[system[k].label for k in keys]))
    out.write("\nGauge pressures: `BAR_GAUGE` ({0}, offset {1:g} bar), `PSI_GAUGE` ({2}). Temperature "
              "differences are shown in K where temperatures are in deg C, and in R where they are in "
              "deg F.\n".format(BAR_GAUGE.label, BAR_GAUGE.offset, PSI_GAUGE.label))

    out.write("\n## Settings presets\n\n")
    out.write(_row("Name", "Points per line", "Saturation points", "Theme", "Label mode", "Page (pt)"))
    out.write(_row(*["---"] * 6))
    for name, s in PRESETS.items():
        out.write(_row("`{0}`".format(name), s.calc.points, s.calc.saturation_points, s.look.name, s.labels.mode,
                       "{0:g} x {1:g}".format(s.page.width_pt, s.page.height_pt)))

    out.write("\n## Themes\n\n")
    out.write(_row("Name", "Background", "Isoline colours (slots)", "Per quantity", "Legend"))
    out.write(_row(*["---"] * 5))
    for name, t in THEMES.items():
        pinned = t.isoline_colors or {}
        per_quantity = ", ".join("{0} {1}".format(q, pinned[q]) for q in ("T", "p", "h", "s", "rho") if q in pinned)
        out.write(_row("`{0}`".format(name), t.axes.background, ", ".join(t.categorical), per_quantity or "-",
                       "yes" if t.axes.legend.visible else "no"))
    with open(path, "w") as f:
        f.write(out.getvalue())
