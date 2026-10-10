# -*- coding: utf-8 -*-
"""Humid air for psychrometric charts, using CoolProp's HAPropsSI.

A psychrometric chart shows moist air at one total pressure: dry-bulb
temperature T on the horizontal axis and humidity ratio W (kg of water
vapour per kg of dry air) on the vertical axis. Lines of constant
relative humidity RH, wet-bulb temperature Twb, specific enthalpy h and
specific volume v (both per kg of dry air) are drawn over it. The
saturation line (RH = 100 %) bounds the chart: states above it would be
fog, so every line is cut where it meets saturation, and the meeting
point is found exactly.

All values are in SI units: K, kg/kg, a fraction 0 to 1 for RH, J/kg and
m3/kg per kg of dry air.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional, Sequence, Tuple

import numpy as np
from CoolProp.HumidAirProp import HAPropsSI

from .isolines import Curve

#: Quantities of humid air: key -> (HAPropsSI name, description).
HUMID_AIR = {
    "T": ("T", "Dry-bulb temperature"),
    "W": ("W", "Humidity ratio"),
    "RH": ("R", "Relative humidity"),
    "Twb": ("B", "Wet-bulb temperature"),
    "Tdp": ("D", "Dew-point temperature"),
    "h": ("H", "Specific enthalpy"),
    "v": ("V", "Specific volume"),
}

#: Families of lines a psychrometric chart can show.
LINE_KEYS = ("RH", "Twb", "h", "v")


@dataclass(frozen=True)
class AirState:
    """A state of humid air in SI units (per kg of dry air)"""
    T: float
    W: float
    RH: float
    Twb: float
    Tdp: float
    h: float
    v: float
    p: float

    def __getitem__(self, key: str) -> float:
        return getattr(self, key)


def _name(key: str) -> str:
    try:
        return HUMID_AIR[key][0]
    except KeyError:
        raise ValueError("Unknown humid-air quantity '{0}', expected one of {1}.".format(key, sorted(HUMID_AIR)))


def humid_air(output: str, key1: str, value1: float, key2: str, value2: float, p_Pa: float) -> float:
    """One property of humid air from two others at total pressure ``p_Pa``."""
    return HAPropsSI(_name(output), _name(key1), value1, "P", p_Pa, _name(key2), value2)


def air_state(key1: str, value1: float, key2: str, value2: float, p_Pa: float = 101325.0) -> AirState:
    """The full state of humid air from two properties, e.g. air_state("T", 298.15, "RH", 0.5)."""
    if key1 == key2:
        raise ValueError("Give two different properties, not '{0}' twice.".format(key1))
    values = {k: humid_air(k, key1, value1, key2, value2, p_Pa) for k in HUMID_AIR}
    return AirState(p=p_Pa, **values)


def saturation_W(T_K, p_Pa: float):
    """Humidity ratio of saturated air at T (array or scalar); NaN where it fails."""
    T = np.atleast_1d(np.asarray(T_K, dtype=float))
    out = np.full_like(T, np.nan)
    for i, t in enumerate(T):
        try:
            out[i] = humid_air("W", "T", t, "RH", 1.0, p_Pa)
        except Exception:
            pass
    return out if np.ndim(T_K) else float(out[0])


@lru_cache(maxsize=32)
def _saturation_grid(T_lo: float, T_hi: float, points: int, p_Pa: float) -> Tuple[float, ...]:
    """Saturation humidity ratios on the temperature grid of the lines, computed once per chart."""
    return tuple(saturation_W(np.linspace(T_lo, T_hi, points), p_Pa))


def _W_on_line(key: str, value: float, T_K: float, p_Pa: float) -> float:
    if key == "RH":
        return humid_air("W", "T", T_K, "RH", value, p_Pa)
    return humid_air("W", "T", T_K, key, value, p_Pa)


def _saturation_crossing(key, value, T_lo, T_hi, p_Pa, iterations=50) -> Optional[float]:
    """Temperature in [T_lo, T_hi] where the line meets saturation, by bisection."""
    def excess(T):
        try:
            return _W_on_line(key, value, T, p_Pa) - saturation_W(T, p_Pa)
        except Exception:
            return math.nan
    f_lo, f_hi = excess(T_lo), excess(T_hi)
    if not (math.isfinite(f_lo) and math.isfinite(f_hi)) or f_lo * f_hi > 0.0:
        return None
    for _ in range(iterations):
        T_mid = 0.5 * (T_lo + T_hi)
        f_mid = excess(T_mid)
        if not math.isfinite(f_mid):
            return None
        if f_mid * f_lo > 0.0:
            T_lo, f_lo = T_mid, f_mid
        else:
            T_hi, f_hi = T_mid, f_mid
        if T_hi - T_lo < 1e-6:
            break
    return 0.5 * (T_lo + T_hi)


def psychro_line(key: str, value: float, p_Pa: float, T_range_K: Tuple[float, float], points: int = 100) -> Curve:
    """A line of constant ``key`` (RH, Twb, h or v) in the T-W plane, in SI units.

    The line is sampled in dry-bulb temperature over ``T_range_K``. Points
    above saturation (fog) or below W = 0 are left out, and the point where
    the line meets saturation is added exactly, so lines start on the
    saturation curve. Lines of wet-bulb temperature start there by
    definition (at T = Twb).
    """
    if key not in LINE_KEYS:
        raise ValueError("Lines of constant '{0}' are not offered, expected one of {1}.".format(key, LINE_KEYS))
    T_lo, T_hi = T_range_K
    T = np.linspace(T_lo, T_hi, points)
    W = np.full_like(T, np.nan)
    n_failed = 0
    falling = key != "RH"   # W falls with T along lines of Twb, h and v
    for i, t in enumerate(T):
        if key == "Twb" and t < value:
            continue   # a wet-bulb line starts on saturation, at T = Twb
        try:
            W[i] = _W_on_line(key, value, t, p_Pa)
        except Exception:
            n_failed += 1
            if falling and np.isfinite(W[:i]).any():
                break   # past W = 0: the rest of the line fails too, and slowly
            continue
        if falling and W[i] < 0.0:
            break
    W_sat = np.array(_saturation_grid(float(T_lo), float(T_hi), int(points), float(p_Pa)))
    inside = np.isfinite(W) & (W >= 0.0) & (W <= W_sat * (1.0 + 1e-9))
    if key == "RH" and value >= 1.0:
        inside = np.isfinite(W)   # the saturation line itself
    xs, ys = list(T[inside]), list(W[inside])
    # Where the line meets saturation, between the last fog point and the first inside one
    if key != "RH" and xs:
        crossing = None
        if key == "Twb" and T_lo <= value <= T_hi:
            crossing = value
        else:
            first = int(np.flatnonzero(inside)[0])
            if first > 0:
                crossing = _saturation_crossing(key, value, float(T[first - 1]), float(T[first]), p_Pa)
        if crossing is not None and crossing < xs[0]:
            xs.insert(0, crossing)
            ys.insert(0, float(saturation_W(crossing, p_Pa)))
    return Curve(np.array(xs), np.array(ys), n_failed)


def chart_ranges(p_Pa: float, T_range_K: Tuple[float, float], W_range: Tuple[float, float]) -> dict:
    """(min, max) of RH, Twb, h and v over the visible part of the chart."""
    T_lo, T_hi = T_range_K
    W_lo, W_hi = W_range
    corners = [(T_lo, W_lo), (T_hi, W_lo), (T_hi, min(W_hi, saturation_W(T_hi, p_Pa))),
               (T_lo, min(W_hi, saturation_W(T_lo, p_Pa)))]
    out = {}
    for key in ("Twb", "h", "v"):
        values = []
        for T, W in corners:
            try:
                values.append(humid_air(key, "T", T, "W", max(W, 1e-9), p_Pa))
            except Exception:
                pass
        if values:
            out[key] = (min(values), max(values))
    out["RH"] = (0.0, 1.0)
    return out


def default_values(key: str, ranges: dict) -> Sequence[float]:
    """Round values for a family over the chart, in SI units."""
    if key == "RH":
        return tuple(round(0.1 * i, 10) for i in range(1, 11))
    lo, hi = ranges[key]
    step = {"Twb": 5.0, "h": 10e3, "v": 0.02}[key]
    offset = 273.15 if key == "Twb" else 0.0   # round in deg C
    first = math.ceil((lo - offset) / step - 1e-9)
    last = math.floor((hi - offset) / step + 1e-9)
    return tuple(round(offset + k * step, 9) for k in range(first, last + 1))
