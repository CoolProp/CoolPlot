# -*- coding: utf-8 -*-
"""Cycles as plain data: how states are given, and a computed cycle.

A cycle is a set of numbered states plus routes through them, given as
chains of state numbers ("loops"). Without explicit loops the states in
order form one closed cycle. Chains may share states, which covers split
cycles, two closed loops on one diagram and injection branches.

This module only describes; :mod:`coolplot.thermo.cycles` computes the
states and the paths between them. No CoolProp, no plotting library.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

from .quantities import quantity_key
from .state import StatePoint

#: How a state given by one property gets its second one from the state
#: before it in the cycle:
#:
#: * "isenthalpic": same specific enthalpy (a throttling valve),
#: * "isentropic": same specific entropy,
#: * "isobaric": same pressure, "isothermal": same temperature,
#:   "isochoric": same density,
#: * "compression" and "expansion": to the given pressure with the
#:   isentropic efficiency ``eta_is`` (1 means isentropic),
#: * "sensible": same humidity ratio, for humid air only (a heating coil,
#:   or a cooling coil that stays above the dew point).
VIA_KINDS = ("isenthalpic", "isentropic", "isobaric", "isothermal", "isochoric", "compression", "expansion",
             "sensible")

#: How the path between two consecutive states is drawn. "auto" picks the
#: process from the two states: equal pressure gives an isobar (which bends
#: along the saturation dome), equal enthalpy an isenthalp, equal entropy
#: an isentrope, equal temperature an isotherm, anything else a
#: "polytropic" path (linear in log p and s). "straight" is a straight line
#: in the diagram.
PATH_KINDS = ("auto", "isobaric", "isenthalpic", "isentropic", "isothermal", "polytropic", "straight")


@dataclass(frozen=True)
class StateInput:
    """How one state of a cycle is given, values in SI units

    Exactly one of these:

    * ``state``: a complete StatePoint (from a cycle model or a measurement);
    * two ``props``, e.g. (("p", 3e5), ("T", 273.15));
    * one ``props`` entry and ``via``, which takes the second property from
      the state before it in the cycle (see VIA_KINDS).
    """
    props: Tuple[Tuple[str, float], ...] = ()
    via: Optional[str] = None
    eta_is: float = 1.0
    state: Optional[StatePoint] = None

    def __post_init__(self):
        props = tuple((quantity_key(k), float(v)) for k, v in self.props)
        object.__setattr__(self, "props", props)
        object.__setattr__(self, "eta_is", float(self.eta_is))
        if self.state is not None:
            if props or self.via:
                raise ValueError("Give a state either as a StatePoint or by its properties, not both.")
            return
        _check_props(props)
        if self.via is None:
            if len(props) != 2:
                raise ValueError("A state needs two properties, or one and 'via', not {0}.".format(dict(props)))
        else:
            _check_via(self.via, props, self.eta_is)

    def to_dict(self) -> dict:
        """The record of docs/reference/contracts.md for this state input."""
        if self.state is not None:
            return {"state": self.state.to_dict()}
        out: Dict[str, Any] = {"props": [list(p) for p in self.props]}
        if self.via is not None:
            out["via"] = self.via
            if self.via in ("compression", "expansion"):
                out["eta_is"] = self.eta_is
        return out

    @classmethod
    def from_dict(cls, data: dict) -> "StateInput":
        """A state input from its record, see :meth:`to_dict`."""
        if "state" in data:
            return cls(state=StatePoint.from_dict(data["state"]))
        return cls(tuple(tuple(p) for p in data.get("props", ())), data.get("via"), data.get("eta_is", 1.0))


def _check_props(props):
    if any(not math.isfinite(v) for _, v in props):
        raise ValueError("State properties have to be finite numbers, not {0}.".format(dict(props)))
    if len({k for k, _ in props}) != len(props):
        raise ValueError("A property is given twice in {0}.".format(dict(props)))


def _check_via(via: str, props, eta_is: float):
    """A via needs one property, a known kind, the outlet pressure for machines, and a usable eta_is."""
    if via not in VIA_KINDS:
        raise ValueError("Unknown via '{0}', expected one of {1}.".format(via, VIA_KINDS))
    if len(props) != 1:
        raise ValueError("A state with via '{0}' needs exactly one property, not {1}.".format(via, dict(props)))
    if via in ("compression", "expansion") and props[0][0] != "p":
        raise ValueError("A {0} is given by its outlet pressure 'p'.".format(via))
    if not 0.0 < eta_is <= 1.0:
        raise ValueError("eta_is has to be between 0 and 1, not {0}.".format(eta_is))


def default_loops(numbers: Sequence[int]) -> Tuple[Tuple[int, ...], ...]:
    """One closed loop through the states in ascending order."""
    numbers = sorted(numbers)
    return (tuple(numbers) + (numbers[0],),) if numbers else ()


def check_loops(numbers: Sequence[int], loops) -> Tuple[Tuple[int, ...], ...]:
    """Validate chains of state numbers; returns them as tuples."""
    loops = tuple(tuple(int(n) for n in chain) for chain in loops)
    known = set(numbers)
    for chain in loops:
        if len(chain) < 2:
            raise ValueError("A chain needs at least two states, not {0}.".format(list(chain)))
        unknown = [n for n in chain if n not in known]
        if unknown:
            raise ValueError("The chain {0} refers to states {1} that are not defined.".format(list(chain), unknown))
    return loops


def check_paths(paths) -> Tuple[Tuple[Tuple[int, int], str], ...]:
    """Validate {(from, to): kind}; returns sorted pairs so the value is hashable."""
    items = paths.items() if isinstance(paths, dict) else paths
    out = []
    for pair, kind in items:
        a, b = (int(n) for n in pair)
        if kind not in PATH_KINDS:
            raise ValueError("Unknown path '{0}' from {1} to {2}, expected one of {3}.".format(kind, a, b, PATH_KINDS))
        out.append(((a, b), kind))
    return tuple(sorted(out))


def _frozen(value: Any) -> Any:
    """``value`` with every list and tuple in it turned into a tuple, recursively."""
    if isinstance(value, (list, tuple)):
        return tuple(_frozen(item) for item in value)
    return value


@dataclass(frozen=True)
class Cycle:
    """A computed cycle: numbered states, routes and results

    This is what the cycle models in :mod:`coolplot.thermo.cycles` return
    and what :meth:`coolplot.PropertyDiagram.add_cycle` accepts.

    Attributes
    ----------
    name : str
        Shown in the legend.
    states : tuple of (number, StatePoint)
        The states in SI units.
    loops : tuple of chains
        Chains of state numbers, each drawn as one connected line.
    paths : tuple of ((from, to), kind)
        Path kinds for connections that should not use "auto".
    results : tuple of (name, value)
        Results in SI units, named like the quantities they hold, for
        example ("COP_heating", 3.9) or ("q_evap_J_kg", 2.6e5).
    fluid : str
        The fluid the states were computed for, as :attr:`coolplot.thermo.Fluid.name`
        gives it; shown in messages.
    fluid_model : tuple
        The model of that fluid, :attr:`coolplot.thermo.Fluid.model_key`:
        backend, components, fractions, their basis and interaction
        parameters, which the name may not hold (a mixture given by mass
        has a name CoolProp reads by mole). The cycle models fill it in;
        a chart checks a cycle against its fluid with it, or with the name
        when it is empty.
    """
    name: str
    states: Tuple[Tuple[int, StatePoint], ...]
    loops: Tuple[Tuple[int, ...], ...] = ()
    paths: Tuple[Tuple[Tuple[int, int], str], ...] = ()
    results: Tuple[Tuple[str, float], ...] = ()
    fluid: str = ""
    fluid_model: Tuple[Any, ...] = ()

    def __post_init__(self):
        states = tuple(sorted((int(n), s) for n, s in (self.states.items() if isinstance(self.states, dict)
                                                         else self.states)))
        object.__setattr__(self, "states", states)
        numbers = [n for n, _ in states]
        object.__setattr__(self, "loops", check_loops(numbers, self.loops) if self.loops else default_loops(numbers))
        object.__setattr__(self, "paths", check_paths(self.paths))
        results = self.results.items() if isinstance(self.results, dict) else self.results
        object.__setattr__(self, "results", tuple((str(k), float(v)) for k, v in results))
        # Lists anywhere in the model become tuples, so that the Cycle stays hashable
        object.__setattr__(self, "fluid_model", _frozen(self.fluid_model))

    def state(self, number: int) -> StatePoint:
        """The state with the given number."""
        return dict(self.states)[number]

    @property
    def result(self) -> Dict[str, float]:
        """The results as a dict, e.g. cycle.result["COP_heating"]."""
        return dict(self.results)
