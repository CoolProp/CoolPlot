# -*- coding: utf-8 -*-
"""Where the properties of a chart come from: references for the badge.

CoolProp names the source of every equation of state with a BibTeX key
(``get_BibTeXKey("R290", "EOS")`` is "Lemmon-JCED-2009") and ships its
bibliography, ``CoolPropBibTeXLibrary.bib``, inside the Python package.
:func:`fluid_references` turns these into short lines for the badge of a
chart (:class:`coolplot.spec.settings.BrandingSettings`):

* a pure fluid of the HEOS backend: its equation of state;
* a mixture: the equation of state of every component, then the
  references of its mixing model (the binary pairs CoolProp has fitted);
* humid air: ASHRAE RP-1485 (Herrmann, Kretzschmar and Gatley), the
  basis of ``HAPropsSI``;
* other backends: the name of the backend (REFPROP, a cubic equation),
  without a reference, since CoolProp cannot name one.

When the bibliography is missing or lacks a key, the line shows the key
itself, which still identifies the source exactly.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from itertools import combinations
from typing import Dict, List, Optional, Tuple

import CoolProp
import CoolProp.CoolProp as CP

from .fluid import Fluid, model_from_string

BIB_FILE = "CoolPropBibTeXLibrary.bib"
#: The BibTeX key of the humid air model behind HAPropsSI.
HUMID_AIR_KEY = "Herrmann-2009"

# LaTeX accent commands as they appear in CoolProp's bibliography, mapped to
# the combining characters of Unicode (written as escapes, the source is ASCII)
_ACCENTS = {"'": "\u0301", "`": "\u0300", '"': "\u0308", "^": "\u0302", "~": "\u0303", "v": "\u030c",
            "c": "\u0327", "r": "\u030a", "=": "\u0304", ".": "\u0307", "u": "\u0306", "H": "\u030b"}
_LETTERS = {"ss": "\u00df", "o": "\u00f8", "O": "\u00d8", "AA": "\u00c5", "aa": "\u00e5", "ae": "\u00e6",
            "AE": "\u00c6", "l": "\u0142", "L": "\u0141", "i": "i"}


def latex_to_text(text: str) -> str:
    """Plain text from the LaTeX of a BibTeX field: accents resolved, braces and commands removed."""
    import unicodedata

    def accent(match):
        letter = match.group(2) or match.group(3)
        return unicodedata.normalize("NFC", letter + _ACCENTS[match.group(1)])

    # {\"u}, \"{u}, \"u, {\v s}, \r{A}
    text = re.sub(r"""\\(['`"^~=.])\s*(?:\{([A-Za-z])\}|([A-Za-z]))""", accent, text)
    text = re.sub(r"\\([vcruH])\s*(?:\{([A-Za-z])\}|\s([A-Za-z]))", accent, text)
    text = re.sub(r"\\(ss|AA|aa|AE|ae|o|O|l|L|i)(?![A-Za-z])", lambda m: _LETTERS[m.group(1)], text)
    text = re.sub(r"\\[A-Za-z]+\s*", "", text)   # any other command
    text = text.replace("{", "").replace("}", "").replace("--", "-")
    return re.sub(r"\s+", " ", text).strip()


def bibliography_path() -> Optional[str]:
    """The bibliography that ships with the installed CoolProp, or None."""
    path = os.path.join(os.path.dirname(CoolProp.__file__), BIB_FILE)
    return path if os.path.isfile(path) else None


@lru_cache(maxsize=1)
def _bibliography() -> Dict[str, Dict[str, str]]:
    path = bibliography_path()
    if path is None:
        return {}
    with open(path, encoding="utf-8", errors="replace") as f:
        return parse_bibtex(f.read())


def parse_bibtex(text: str) -> Dict[str, Dict[str, str]]:
    """Entries of a BibTeX file: key -> {"type": ..., field name (lower case): raw value}.

    Enough for CoolProp's bibliography: fields in braces (nested braces
    allowed) or quotes, or bare numbers.
    """
    entries = {}
    for match in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", text):
        kind, key = match.group(1).lower(), match.group(2)
        if kind in ("comment", "string", "preamble"):
            continue
        fields, pos = {"type": kind}, match.end()
        while True:
            field = re.match(r"\s*(\w+)\s*=\s*", text[pos:])
            if field is None:
                break
            name, pos = field.group(1).lower(), pos + field.end()
            value, pos = _bibtex_value(text, pos)
            fields[name] = value
            comma = re.match(r"\s*,", text[pos:])
            if comma is None:
                break
            pos += comma.end()
        entries[key] = fields
    return entries


def _bibtex_value(text: str, pos: int) -> Tuple[str, int]:
    """(value, position after it) of one field value starting at ``pos``."""
    if pos < len(text) and text[pos] == "{":
        depth, start = 0, pos
        while pos < len(text):
            if text[pos] == "{":
                depth += 1
            elif text[pos] == "}":
                depth -= 1
                if depth == 0:
                    return text[start + 1:pos], pos + 1
            pos += 1
        return text[start + 1:], len(text)
    if pos < len(text) and text[pos] == '"':
        end = text.find('"', pos + 1)
        end = len(text) if end < 0 else end
        return text[pos + 1:end], end + 1
    match = re.match(r"[^,}\s]*", text[pos:])
    return match.group(0), pos + match.end()


def _last_names(authors: str) -> List[str]:
    names = []
    for author in re.split(r"\s+and\s+", latex_to_text(authors)):
        author = author.strip()
        if not author:
            continue
        names.append(author.split(",")[0].strip() if "," in author else author.split()[-1])
    return names


def _authors_short(authors: str) -> str:
    names = _last_names(authors)
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return "{0} and {1}".format(*names)
    return names[0] + " et al."


def cite(key: str, style: str = "short") -> str:
    """One reference as text: "Lemmon et al. (2009)" ("short") or with the
    journal, volume and pages ("full"). The key itself when the
    bibliography does not have it."""
    entry = _bibliography().get(key)
    if entry is None or "author" not in entry:
        return key
    authors = _authors_short(entry["author"])
    year = latex_to_text(entry.get("year", ""))
    if style == "short":
        return "{0} ({1})".format(authors, year) if year else authors
    if entry["type"] == "article" and "journal" in entry:
        source = latex_to_text(entry["journal"])
        if entry.get("volume"):
            source += " " + latex_to_text(entry["volume"])
        source += " ({0})".format(year) if year else ""
        if entry.get("pages"):
            source += " " + latex_to_text(entry["pages"])
        return "{0}, {1}".format(authors, source)
    # Reports, theses, books: the title up to its first colon names them best
    title = latex_to_text(entry.get("title", "")).split(":")[0].strip()
    source = title or latex_to_text(entry.get("institution", entry.get("publisher", "")))
    return "{0}, {1} ({2})".format(authors, source, year) if source else "{0} ({1})".format(authors, year)


def _pair_key(a: str, b: str) -> Optional[str]:
    """The BibTeX key of the binary pair of two components, in either order, or None."""
    cas = [CP.get_fluid_param_string(name, "CAS") for name in (a, b)]
    for first, second in (cas, cas[::-1]):
        try:
            return CP.get_mixture_binary_pair_data(first, second, "BibTeX")
        except Exception:   # CoolProp raises ValueError (or RuntimeError) for an unknown pair
            continue
    return None


def _short_backend(name: str) -> str:
    """The short name of a CoolProp backend, as in fluid strings: "HelmholtzEOSBackend" -> "HEOS"."""
    name = name.split("&")[-1]   # tabular backends ("BICUBIC&HEOS") use the equation of state behind them
    for part, short in (("Helmholtz", "HEOS"), ("REFPROP", "REFPROP"), ("PengRobinson", "PR"), ("SRK", "SRK"),
                        ("Incompressible", "INCOMP")):
        if part in name:
            return short
    return name


def fluid_references(fluid, style: str = "short") -> Tuple[str, ...]:
    """Lines naming the sources of a fluid's properties, see the module docstring.

    ``fluid`` is a :class:`coolplot.thermo.Fluid`, a FluidSpec (or any
    object with ``backend`` and ``components``), a fluid string or a
    HumidAirSpec; ``style`` is "short" or "full". Only a predefined blend
    ("R407C.mix") needs a CoolProp state, to find its components.
    """
    if style not in ("short", "full"):
        raise ValueError("Unknown reference style {0!r}, expected 'short' or 'full'.".format(style))
    if getattr(fluid, "kind", None) == "humid_air" or type(fluid).__name__ in ("HumidAirSpec", "HumidAir"):
        return ("Humid air: " + cite(HUMID_AIR_KEY, style),)
    if isinstance(fluid, Fluid):
        backend, components = fluid.model_key[0], fluid.model_key[1]
    elif isinstance(fluid, str):
        backend, components = model_from_string(fluid)[:2]
    else:
        backend, components = fluid.backend, tuple(fluid.components)
    backend = _short_backend(backend)
    if backend == "HEOS" and len(components) == 1 and components[0].lower().endswith(".mix"):
        components = _blend_components(components[0])
    return _fluid_lines(backend, tuple(components), style)


@lru_cache(maxsize=64)
def _blend_components(name: str) -> Tuple[str, ...]:
    """The components of a predefined blend such as "R407C.mix"."""
    return tuple(Fluid("HEOS::" + name).model_key[1])


@lru_cache(maxsize=256)
def _fluid_lines(backend: str, components: Tuple[str, ...], style: str) -> Tuple[str, ...]:
    if backend != "HEOS":
        names = ", ".join(components)
        labels = {"REFPROP": "REFPROP", "PR": "Peng-Robinson equation of state",
                  "SRK": "Soave-Redlich-Kwong equation of state", "INCOMP": "CoolProp incompressible fluid"}
        return ("{0}: {1}".format(names, labels.get(backend, backend + " backend of CoolProp")),)
    lines = []
    for name in components:
        try:
            key = CP.get_BibTeXKey(name, "EOS")
        except Exception:   # an unknown name: nothing to cite
            continue
        lines.append("{0}: {1}".format(name, cite(key, style)))
    if len(components) > 1:
        keys = []
        for a, b in combinations(components, 2):
            key = _pair_key(a, b)
            if key and key not in keys:
                keys.append(key)
        if keys:
            lines.append("Mixture model: " + "; ".join(cite(k, style) for k in keys))
    return tuple(lines)


def versions_line() -> str:
    """"CoolProp 8.1.0dev (83f3ca3), CoolPlot 1.2.0.dev0"; the git revision only for development builds."""
    from ..__version__ import __version__ as coolplot_version
    version = CoolProp.__version__
    if "dev" in version:
        revision = str(getattr(CoolProp, "__gitrevision__", "") or "")[:7]
        if revision:
            version += " ({0})".format(revision)
    return "CoolProp {0}, CoolPlot {1}".format(version, coolplot_version)
