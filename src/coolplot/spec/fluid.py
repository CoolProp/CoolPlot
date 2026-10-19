# -*- coding: utf-8 -*-
"""Which fluid a diagram shows, as plain data.

A :class:`FluidSpec` describes the fluid model completely: the CoolProp
backend, the components, their fractions and any binary interaction
parameters a user changed. It is immutable and hashable, so it can serve
as a cache key, and it can be saved as JSON. It does not import CoolProp;
the thermo layer turns it into a working CoolProp state.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Tuple

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

    def __post_init__(self):
        components = tuple(str(c).strip() for c in self.components)
        if not components or not all(components):
            raise ValueError("A FluidSpec needs at least one component name.")
        fractions = tuple(float(f) for f in self.fractions)
        if fractions and len(fractions) != len(components):
            raise ValueError("Got {0} fractions for {1} components.".format(len(fractions), len(components)))
        if any(not 0.0 <= f <= 1.0 for f in fractions):
            raise ValueError("Fractions have to be between 0 and 1, not {0}.".format(fractions))
        if len(components) > 1:
            if not fractions:
                raise ValueError("A mixture of {0} needs fractions.".format(" & ".join(components)))
            if abs(sum(fractions) - 1.0) > 1e-6:
                raise ValueError("The fractions of a mixture have to add up to 1, not {0}.".format(sum(fractions)))
        if self.basis not in BASES:
            raise ValueError("Unknown fraction basis '{0}', expected one of {1}.".format(self.basis, BASES))
        interactions = tuple((int(i), int(j), str(key), float(value)) for i, j, key, value in self.interactions)
        for i, j, _, _ in interactions:
            if not (0 <= i < len(components) and 0 <= j < len(components) and i != j):
                raise ValueError("Interaction parameter for components ({0}, {1}) of {2}.".format(
                    i, j, len(components)))
        object.__setattr__(self, "backend", str(self.backend).strip() or "HEOS")
        object.__setattr__(self, "components", components)
        object.__setattr__(self, "fractions", fractions)
        object.__setattr__(self, "interactions", interactions)

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
