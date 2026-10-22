# -*- coding: utf-8 -*-
"""Which quantities go on the axes of a chart, and which lines it offers.

A diagram is named after its axes with the vertical axis first, as is
customary: "ph" is pressure over specific enthalpy (the log(p)-h chart),
"Ts" is temperature over specific entropy. The psychrometric chart puts
humidity ratio over dry-bulb temperature, "WT"; "psychrometric" is
accepted as its name too. The Mollier h,x chart of European practice
puts its temperature scale "Thx" over the humidity ratio, "ThxW", also
named "mollier" or "hx"; it writes the humidity ratio x and the relative
humidity phi.

Every chart has a kind, "fluid" or "humid_air", which says what computes
its states (a CoolProp AbstractState, or HAPropsSI for humid air). The
kind decides which quantities can be axes and which families of lines
can be drawn; see :data:`FAMILIES`.

This module has no CoolProp dependency; it only knows quantity keys.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, Union

from .quantities import get_quantity, quantity_key

KINDS = ("fluid", "humid_air")


@dataclass(frozen=True)
class Family:
    """How one family of lines (lines of constant ``key``) is drawn

    Attributes
    ----------
    key : str
        The quantity held constant along the lines.
    sweep : str
        The quantity stepped through to compute a line. For fluids it is
        always temperature or pressure, because CoolProp's flash routines
        are fast and reliable for the input pairs this produces (PT,
        HmassP, PSmass, DmassT). Stepping along a plot axis instead, as
        older versions did, needs pairs like HmassSmass or HmassT that are
        slow or unsupported for many fluids. Humid-air lines are stepped
        in dry-bulb temperature.
    edges : tuple of str
        Preferred edges of the frame for the labels of this family, best
        first; ``Settings.labels.edges`` can override them.
    default_num : int
        How many lines a chart gets when the user gives no values.
    bounds : (low, high) or None
        Values outside have no line (vapour quality, relative humidity).
    low_included : bool
        Whether the low bound itself has a line: quality 0 is the
        saturated liquid line, relative humidity 0 is the dry-air axis.
    boundary : tuple of float
        Values that mark the phase boundary and are drawn in the
        saturation style: quality 0 and 1, relative humidity 1.
    """
    key: str
    sweep: str
    edges: Tuple[str, ...]
    default_num: int = 15
    bounds: Optional[Tuple[float, float]] = None
    low_included: bool = True
    boundary: Tuple[float, ...] = ()

    def has_line(self, value_SI: float) -> bool:
        """Whether a line of this value exists at all."""
        if self.bounds is None:
            return True
        low, high = self.bounds
        return (low <= value_SI if self.low_included else low < value_SI) and value_SI <= high

    def check_values(self, values_SI, label: str):
        """Raise ValueError if one of the values has no line."""
        bad = [v for v in values_SI if not self.has_line(v)]
        if bad and self.bounds is not None:   # without bounds every value has a line
            low, high = self.bounds
            span = "between {0:g} and {1:g}" if self.low_included else "above {0:g} and up to {1:g}"
            raise ValueError("{0} has to lie {1} (as an SI value), not {2}.".format(
                label, span.format(low, high), bad))

    @property
    def on_boundary(self) -> bool:
        """Whether the family includes the phase boundary (quality, relative humidity)."""
        return bool(self.boundary)


#: The line families of every chart kind.
FAMILIES = {
    "fluid": (
        Family("T", "p", ("top", "right")),
        Family("p", "T", ("right", "left")),
        Family("h", "p", ("top", "bottom")),
        Family("s", "p", ("top", "right")),
        Family("rho", "T", ("right", "top")),
        Family("u", "p", ("top", "bottom")),
        # Lines of constant quality are traced through saturation states
        Family("Q", "T", ("bottom", "top"), default_num=11, bounds=(0.0, 1.0), boundary=(0.0, 1.0)),
    ),
    "humid_air": (
        # Isotherms are a family only where T is no axis (the Mollier chart);
        # they are stepped in the humidity ratio
        Family("T", "W", ("right", "left"), default_num=12),
        Family("RH", "T", ("right", "top"), default_num=11, bounds=(0.0, 1.0), low_included=False,
               boundary=(1.0,)),
        Family("Twb", "T", ("bottom", "left"), default_num=9),
        Family("h", "T", ("bottom", "left"), default_num=13),
        Family("v", "T", ("bottom", "right"), default_num=10),
    ),
}

#: What set_lines does when not told: a property diagram draws evenly
#: spaced unlabelled lines, a psychrometric chart round labelled ones.
LINE_DEFAULTS = {
    "fluid": {"rounding": False, "labels": False},
    "humid_air": {"rounding": True, "labels": True},
}

#: Quantities that can be on an axis, per chart kind.
AXES = {
    "fluid": ("T", "p", "h", "s", "rho", "u"),
    "humid_air": ("T", "W", "Thx"),
}

#: Chart kinds whose lines are computed for given orientations only: (y, x)
#: pairs. Humid air: the psychrometric chart and the Mollier h,x chart.
FIXED_AXES = {
    "humid_air": (("W", "T"), ("Thx", "W")),
}

#: Symbols that differ from the quantity's own in one diagram: the Mollier
#: chart writes the humidity ratio x and the relative humidity phi.
_SYMBOLS = {
    ("Thx", "W", "humid_air"): {"W": "x", "RH": "phi"},
}

#: Axis titles that differ from the quantity's name in one chart kind.
_AXIS_NAMES = {
    "humid_air": {"T": "Dry-bulb temperature"},
}

_NAMES = {
    "TS": ("T", "s", "fluid"), "PH": ("p", "h", "fluid"), "HS": ("h", "s", "fluid"), "PS": ("p", "s", "fluid"),
    "PD": ("p", "rho", "fluid"), "PRHO": ("p", "rho", "fluid"), "TD": ("T", "rho", "fluid"),
    "TRHO": ("T", "rho", "fluid"), "PT": ("p", "T", "fluid"),
    "WT": ("W", "T", "humid_air"), "PSYCHROMETRIC": ("W", "T", "humid_air"),
    "THXW": ("Thx", "W", "humid_air"), "MOLLIER": ("Thx", "W", "humid_air"), "HX": ("Thx", "W", "humid_air"),
}


@dataclass(frozen=True)
class DiagramType:
    """The pair of quantities on the axes, and the kind of chart

    Attributes
    ----------
    y : str
        Quantity key on the vertical axis.
    x : str
        Quantity key on the horizontal axis.
    kind : str
        "fluid" (a CoolProp fluid) or "humid_air".
    """
    y: str
    x: str
    kind: str = "fluid"

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError("Unknown chart kind '{0}', expected one of {1}.".format(self.kind, KINDS))
        y, x = quantity_key(self.y), quantity_key(self.x)
        for key in (y, x):
            if key not in AXES[self.kind]:
                raise ValueError("'{0}' cannot be an axis of a {1} chart, expected one of {2}.".format(
                    key, self.kind, AXES[self.kind]))
        if x == y:
            raise ValueError("The axes of a diagram have to show different quantities, not '{0}' twice.".format(x))
        if self.kind in FIXED_AXES and (y, x) not in FIXED_AXES[self.kind]:
            offered = " or ".join("{0} over {1}".format(*pair) for pair in FIXED_AXES[self.kind])
            raise ValueError("A {0} chart shows {1}; '{2}{3}' is not offered.".format(self.kind, offered, y, x))
        object.__setattr__(self, "y", y)
        object.__setattr__(self, "x", x)

    @classmethod
    def parse(cls, name: Union[str, "DiagramType"]) -> "DiagramType":
        """Build from a name like "ph", "Ts", "PH", "WT" or an existing DiagramType."""
        if isinstance(name, DiagramType):
            return name
        name = str(name)
        if name.upper() in _NAMES:
            y, x, kind = _NAMES[name.upper()]
            return cls(y=y, x=x, kind=kind)
        # Any other pair of fluid axis quantities, vertical axis first: a
        # DiagramType("T", "h") is written as "Th" and has to read back.
        # coolplot-core (cpp/src/core.cpp) reads names the same way.
        for i in range(1, len(name)):
            try:
                candidate = cls(y=name[:i], x=name[i:], kind="fluid")
            except (KeyError, ValueError):
                continue
            if candidate.name == name:
                return candidate
        raise ValueError("Unknown diagram type '{0}', expected one of {1} or two fluid axis "
                         "quantities such as 'Th'.".format(name, sorted(n.lower() for n in _NAMES)))

    @property
    def name(self) -> str:
        """The name of the diagram type, vertical axis first, e.g. "ph"."""
        return self.y + self.x

    @property
    def x_log(self) -> bool:
        """Whether the horizontal axis is logarithmic."""
        return get_quantity(self.x).log_scale

    @property
    def y_log(self) -> bool:
        """Whether the vertical axis is logarithmic."""
        return get_quantity(self.y).log_scale

    @property
    def families(self) -> Tuple[Family, ...]:
        """The line families this chart can draw, in their usual order."""
        return tuple(f for f in FAMILIES[self.kind] if f.key not in (self.x, self.y))

    def family(self, iso_key: str) -> Optional[Family]:
        """The family of lines of constant ``iso_key``, or None if unsupported.

        A line of constant x or constant y is a straight line parallel to an
        axis and is not offered as an isoline; use the grid for that.
        """
        iso_key = quantity_key(iso_key)
        return next((f for f in self.families if f.key == iso_key), None)

    def require_family(self, iso_key: str) -> Family:
        """The family of lines of constant ``iso_key``; KeyError if the diagram does not offer it.

        For keys that are known to be supported, such as those of the
        isolines of a spec, where :meth:`family` would never give None.
        """
        family = self.family(iso_key)
        if family is None:
            raise KeyError("The {0}-{1} diagram has no lines of constant {2}.".format(self.y, self.x, iso_key))
        return family

    def sweep_quantity(self, iso_key: str) -> Optional[str]:
        """Quantity stepped through to compute an isoline, or None if unsupported."""
        family = self.family(iso_key)
        return None if family is None else family.sweep

    def supports(self, iso_key: str) -> bool:
        """Whether lines of constant ``iso_key`` can be drawn in this diagram."""
        return self.family(iso_key) is not None

    def supported_isolines(self):
        """Quantity keys that can be drawn as isolines in this diagram."""
        return [f.key for f in self.families]

    @property
    def line_defaults(self) -> dict:
        """Default ``rounding`` and ``labels`` of set_lines for this kind of chart."""
        return LINE_DEFAULTS[self.kind]

    def symbol(self, key: str) -> str:
        """The symbol of a quantity in this diagram, e.g. "W", or "x" on the Mollier chart."""
        key = quantity_key(key)
        return _SYMBOLS.get((self.y, self.x, self.kind), {}).get(key, get_quantity(key).symbol)

    @property
    def is_mollier(self) -> bool:
        """Whether this is the Mollier h,x chart (temperature scale over humidity ratio)."""
        return self.kind == "humid_air" and self.y == "Thx"

    def quantity_label(self, key: str) -> str:
        """The name of a quantity in this kind of chart, e.g. "Dry-bulb temperature"."""
        key = quantity_key(key)
        return _AXIS_NAMES.get(self.kind, {}).get(key, get_quantity(key).label)
