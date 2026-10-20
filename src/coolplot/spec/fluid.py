# -*- coding: utf-8 -*-
"""Which fluid a chart shows, as plain data.

A :class:`FluidSpec` describes a CoolProp fluid model completely: the CoolProp
backend, the components, their fractions and any binary interaction
parameters a user changed. It is immutable and hashable, so it can serve
as a cache key, and it can be saved as JSON. It does not import CoolProp;
the thermo layer turns it into a working CoolProp state.
:class:`HumidAirSpec` is the counterpart for psychrometric charts: humid
air at one total pressure. Both carry a ``kind`` that names the property
provider of the thermo layer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Tuple

from ..core.limits import HUMID_AIR_P_LIMITS_PA, HUMID_AIR_T_LIMITS_K, within

BASES = ("mole", "mass", "volu")

# A component in a fluid string: a name, optionally followed by a fraction
# in square brackets, e.g. "R32[0.7]".
_COMPONENT = re.compile(r"^\s*([^\[\]&]+?)\s*(?:\[\s*([^\]]+?)\s*\])?\s*$")


@dataclass(frozen=True)
class FluidSpec:
    """A fluid model as data

    Attributes
    ----------
    backend : str
        CoolProp backend, e.g. "HEOS", "REFPROP", "INCOMP", "BICUBIC&HEOS".
    components : tuple of str
        Fluid names as CoolProp knows them, e.g. ("R32", "R125").
    fractions : tuple of float
        One fraction per component, or empty for a pure fluid. A single
        fraction is used for incompressible solutions such as MEG[0.3].
    basis : str
        What the fractions mean: "mole", "mass" or "volu".
    interactions : tuple of (i, j, parameter, value)
        Binary interaction parameters set after the fractions, for example
        (0, 1, "betaT", 1.02).
    """
    backend: str = "HEOS"
    components: Tuple[str, ...] = ()
    fractions: Tuple[float, ...] = ()
    basis: str = "mole"
    interactions: Tuple[Tuple[int, int, str, float], ...] = ()

    kind = "fluid"

    def __post_init__(self):
        components = tuple(str(c).strip() for c in self.components)
        if not components or not all(components):
            raise ValueError("A FluidSpec needs at least one component name.")
        fractions = _checked_fractions(components, self.fractions)
        if self.basis not in BASES:
            raise ValueError("Unknown fraction basis '{0}', expected one of {1}.".format(self.basis, BASES))
        object.__setattr__(self, "backend", str(self.backend).strip() or "HEOS")
        object.__setattr__(self, "components", components)
        object.__setattr__(self, "fractions", fractions)
        object.__setattr__(self, "interactions", _checked_interactions(components, self.interactions))

    @classmethod
    def parse(cls, text: str, basis: str = None) -> "FluidSpec":
        """Read a CoolProp fluid string.

        Examples: "R290", "HEOS::R290", "HEOS::R32[0.7]&R125[0.3]",
        "INCOMP::MEG[0.3]". Without a backend, "HEOS" is used. The fractions
        are mole fractions, except for the INCOMP backend where CoolProp
        reads them as mass fractions; ``basis`` overrides this.
        """
        if isinstance(text, FluidSpec):
            return text
        text = str(text).strip()
        backend, sep, names = text.partition("::")
        if not sep:
            backend, names = "HEOS", text
        components, fractions = _split_components(names, text)
        if fractions and len(fractions) != len(components):
            raise ValueError("Give a fraction for every component or for none in '{0}'.".format(text))
        if basis is None:
            basis = "mass" if backend.upper() == "INCOMP" else "mole"
        return cls(backend, tuple(components), tuple(fractions), basis)

    def __str__(self):
        """The CoolProp fluid string (interaction parameters are not part of it)."""
        if self.fractions:
            names = "&".join("{0}[{1:.12g}]".format(c, f) for c, f in zip(self.components, self.fractions))
        else:
            names = "&".join(self.components)
        return "{0}::{1}".format(self.backend, names)

    @property
    def name(self) -> str:
        """Short name for titles, e.g. "R32[0.7]&R125[0.3]"."""
        return str(self).split("::", 1)[1]

    def to_dict(self) -> dict:
        return {"backend": self.backend, "components": list(self.components),
                "fractions": list(self.fractions), "basis": self.basis,
                "interactions": [list(x) for x in self.interactions]}

    @classmethod
    def from_dict(cls, data: dict) -> "FluidSpec":
        return cls(data.get("backend", "HEOS"), tuple(data["components"]), tuple(data.get("fractions", ())),
                   data.get("basis", "mole"), tuple(tuple(x) for x in data.get("interactions", ())))


def _split_components(names: str, text: str):
    """Component names and their fractions (if given) from "R32[0.7]&R125[0.3]"."""
    components, fractions = [], []
    for part in names.split("&"):
        match = _COMPONENT.match(part)
        if match is None:
            raise ValueError("Cannot read the fluid string '{0}'.".format(text))
        components.append(match.group(1))
        if match.group(2) is not None:
            try:
                fractions.append(float(match.group(2)))
            except ValueError:
                raise ValueError("Cannot read the fraction '{0}' in '{1}'.".format(match.group(2), text))
    return components, fractions


def _checked_fractions(components, fractions) -> Tuple[float, ...]:
    """Fractions as floats: one per component or none, between 0 and 1, adding up to 1 for a mixture."""
    fractions = tuple(float(f) for f in fractions)
    if fractions and len(fractions) != len(components):
        raise ValueError("Got {0} fractions for {1} components.".format(len(fractions), len(components)))
    if any(not 0.0 <= f <= 1.0 for f in fractions):
        raise ValueError("Fractions have to be between 0 and 1, not {0}.".format(fractions))
    if len(components) > 1:
        if not fractions:
            raise ValueError("A mixture of {0} needs fractions.".format(" & ".join(components)))
        if abs(sum(fractions) - 1.0) > 1e-6:
            raise ValueError("The fractions of a mixture have to add up to 1, not {0}.".format(sum(fractions)))
    return fractions


def _checked_interactions(components, interactions) -> Tuple[Tuple[int, int, str, float], ...]:
    """Binary interaction parameters as (i, j, key, value), between two different components."""
    checked = tuple((int(i), int(j), str(key), float(value)) for i, j, key, value in interactions)
    for i, j, _, _ in checked:
        if not (0 <= i < len(components) and 0 <= j < len(components) and i != j):
            raise ValueError("Interaction parameter for components ({0}, {1}) of {2}.".format(
                i, j, len(components)))
    return checked


@dataclass(frozen=True)
class HumidAirSpec:
    """Humid air at one total pressure, computed with CoolProp's HAPropsSI

    The states of humid air are per kg of dry air. ``kind`` tells the
    thermo layer which property provider to build; :class:`FluidSpec`
    has kind "fluid".
    """
    p_Pa: float = 101325.0

    kind = "humid_air"
    T_LIMITS_K = HUMID_AIR_T_LIMITS_K
    P_LIMITS_PA = HUMID_AIR_P_LIMITS_PA

    def __post_init__(self):
        p_Pa = float(self.p_Pa)
        if not within(p_Pa, self.P_LIMITS_PA):
            raise ValueError("The total pressure has to lie between {0} and {1} Pa for HAPropsSI, not {2} Pa "
                             "(bar with units='engineering', Pa with 'SI').".format(
                                 self.P_LIMITS_PA[0], self.P_LIMITS_PA[1], p_Pa))
        object.__setattr__(self, "p_Pa", p_Pa)

    @property
    def name(self) -> str:
        """Short name for titles and messages."""
        return "humid air at {0:.6g} Pa".format(self.p_Pa)

    def __str__(self):
        return self.name

    def to_dict(self) -> dict:
        return {"model": "humid_air", "p_Pa": self.p_Pa}

    @classmethod
    def from_dict(cls, data: dict) -> "HumidAirSpec":
        return cls(float(data.get("p_Pa", 101325.0)))


def fluid_spec_from_dict(data) -> "FluidSpec | HumidAirSpec":
    """The fluid of a saved spec: a FluidSpec, or a HumidAirSpec when the
    data says ``"model": "humid_air"``."""
    if isinstance(data, dict) and data.get("model") == "humid_air":
        return HumidAirSpec.from_dict(data)
    return FluidSpec.from_dict(data)
