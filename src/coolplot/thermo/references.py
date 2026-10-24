# -*- coding: utf-8 -*-
"""Where the properties of a chart come from: references for the badge.

CoolProp names the source of every equation of state with a BibTeX key
(``get_BibTeXKey("R290", "EOS")`` is "Lemmon-JCED-2009") and ships its
bibliography, ``CoolPropBibTeXLibrary.bib``, inside the Python package.
:func:`fluid_references` turns these into short lines for the badge of a
chart (:class:`coolplot.spec.settings.BrandingSettings`):

* a pure fluid of the HEOS backend: its equation of state;
* a mixture: first its name and composition ("R407C: R32 23 %, R125
  25 %, R134a 52 % by mass"), then the equation of state of every
  component, then the references of its mixing model (the binary pairs
  CoolProp has fitted). A mixture given by its fractions is named after
  the predefined blend of CoolProp with the same composition, if there is
  one, else "Mixture";
* humid air: ASHRAE RP-1485 (Herrmann, Kretzschmar and Gatley), the
  basis of ``HAPropsSI``;
* other backends: the name of the backend (REFPROP, a cubic equation),
  without a reference, since CoolProp cannot name one; with the fractions
  of a mixture or a solution ("MEG 30 % by mass").

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

from ..core.numbers import format_number
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
    # Inline math such as $_3$ or $^{13}$: the characters, without the markup
    text = re.sub(r"\$([^$]*)\$", lambda m: re.sub(r"[_^{}\\]", "", m.group(1)), text)
    text = re.sub(r"\\([&%$#_])", r"\1", text)   # escaped special characters: \& -> &
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
    assert match is not None   # the pattern also matches an empty string
    return match.group(0), pos + match.end()


#: Name suffixes that are not a family name: "Rachford Jr." is cited as "Rachford".
_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"}


def _split_top(text: str, separator: str) -> List[str]:
    """``text`` split at ``separator`` (a regular expression) outside braces."""
    parts, depth, start = [], 0, 0
    for match in re.finditer(r"[{}]|" + separator, text):
        token = match.group(0)
        if token == "{":
            depth += 1
        elif token == "}":
            depth = max(depth - 1, 0)
        elif depth == 0:
            parts.append(text[start:match.start()])
            start = match.end()
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


def _last_name(author: str) -> str:
    """The family name of one BibTeX author, with its particles ("de Vries").

    "Last, First" gives what stands before the comma; "First von Last" gives
    the words from the first lower-case one after the first word ("von",
    "de", "van der") on, or else the last word; a braced group counts as
    one word; a trailing "Jr." or "II" is dropped, also inside braces.
    This differs from BibTeX in a few cases on purpose: "Stanley E. Babb
    Jr." gives "Babb" (BibTeX: "Jr."), "{Rachford Jr.}" gives "Rachford".
    A name without a first name that starts with a particle ("van der
    Waals") loses the particle.
    """
    parts = _split_top(author, ",")
    if len(parts) > 1:
        words = _split_top(parts[0], r"\s+")
    else:
        words = _split_top(author, r"\s+")
        while len(words) > 1 and latex_to_text(words[-1]).lower() in _SUFFIXES:
            words.pop()
        start = next((i for i, w in enumerate(words[:-1]) if i > 0 and latex_to_text(w)[:1].islower()), None)
        words = words[start:] if start is not None else words[-1:]
    text = latex_to_text(" ".join(words))
    tokens = text.split()
    while len(tokens) > 1 and tokens[-1].lower() in _SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _last_names(authors: str) -> List[str]:
    return [_last_name(a) for a in _split_top(authors, r"\s+and\s+")]


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
        backend, components, fractions, basis = fluid.model_key[:4]
    elif isinstance(fluid, str):
        backend, components, fractions, basis = model_from_string(fluid)[:4]
    else:
        backend, components = fluid.backend, tuple(fluid.components)
        fractions, basis = tuple(getattr(fluid, "fractions", ())), getattr(fluid, "basis", "mole")
    backend = _short_backend(backend)
    blend = ""
    if backend == "HEOS" and len(components) == 1 and components[0].lower().endswith(".mix"):
        blend = components[0][:-len(".mix")]
        components, fractions = _blend_composition(components[0])
        basis = "mole"
    return _fluid_lines(backend, tuple(components), tuple(float(f) for f in fractions), basis, blend, style)


@lru_cache(maxsize=64)
def _blend_composition(name: str) -> Tuple[Tuple[str, ...], Tuple[float, ...]]:
    """(components, mole fractions) of a predefined blend such as "R407C.mix"."""
    model_key = Fluid("HEOS::" + name).model_key
    return tuple(model_key[1]), tuple(model_key[2])


# Composition of mixtures -----------------------------------------------------

#: How far (in mass fraction) a mixture may be from a predefined blend of
#: CoolProp to carry its name: half a percent, finer than the steps
#: between blends of the same components (R407A, R407C, R407F, R407H).
BLEND_TOLERANCE = 0.005

_BASIS_WORDS = {"mole": "by mole", "mass": "by mass", "volu": "by volume"}


def _mass_fractions(components: Tuple[str, ...], fractions: Tuple[float, ...]) -> Optional[Tuple[float, ...]]:
    """Mass fractions from mole fractions, w_i = x_i M_i / sum(x_j M_j); None if CoolProp lacks a molar mass."""
    try:
        weights = [x * CP.PropsSI("molar_mass", name) for x, name in zip(fractions, components)]
    except Exception:   # a name the HEOS backend does not know
        return None
    total = sum(weights)
    return tuple(w / total for w in weights) if total > 0.0 else None


@lru_cache(maxsize=1)
def _predefined_blends() -> Dict[frozenset, List[Tuple[str, Dict[str, float]]]]:
    """The predefined blends of CoolProp by their set of components: [(name, {component: mass fraction})].

    CoolProp lists every blend twice ("R407C.mix" and "R407C.MIX"); the
    first spelling is used. A blend whose components CoolProp cannot load
    is left out.
    """
    blends: Dict[frozenset, List[Tuple[str, Dict[str, float]]]] = {}
    for name in CP.get_global_param_string("predefined_mixtures").split(","):
        if not name.endswith(".mix"):
            continue
        try:
            state = CP.AbstractState("HEOS", name)
            components, mass = tuple(state.fluid_names()), tuple(state.get_mass_fractions())
        except Exception:   # components or parameters missing in this CoolProp
            continue
        blends.setdefault(frozenset(components), []).append((name[:-len(".mix")], dict(zip(components, mass))))
    return blends


@lru_cache(maxsize=256)
def _canonical_name(name: str) -> str:
    """CoolProp's own name of a fluid, e.g. "Nitrogen" for the alias "N2"; the name itself if unknown."""
    try:
        return CP.get_fluid_param_string(name, "name")
    except Exception:   # not a fluid of the HEOS library
        return name


def blend_name(components: Tuple[str, ...], mass_fractions: Tuple[float, ...]) -> str:
    """The name of the predefined blend of CoolProp with this composition, e.g. "R410A", or "".

    Matches when every mass fraction is within :data:`BLEND_TOLERANCE`;
    of several matches the closest one wins. Components may be given by
    an alias of CoolProp ("N2" for Nitrogen).
    """
    components = tuple(_canonical_name(c) for c in components)
    best, best_distance = "", BLEND_TOLERANCE
    for name, blend in _predefined_blends().get(frozenset(components), ()):
        distance = max(abs(blend[c] - w) for c, w in zip(components, mass_fractions))
        if distance <= best_distance:
            best, best_distance = name, distance
    return best


def composition_text(components: Tuple[str, ...], fractions: Tuple[float, ...], basis: str) -> str:
    """"R32 70 %, R125 30 % by mole": every component with its fraction in per cent."""
    parts = ["{0} {1} %".format(name, format_number(100.0 * f, 3)) for name, f in zip(components, fractions)]
    return "{0} {1}".format(", ".join(parts), _BASIS_WORDS.get(basis, "by " + basis))


def _composition_line(backend: str, components: Tuple[str, ...], fractions: Tuple[float, ...], basis: str,
                      blend: str) -> str:
    """"R407C: R32 23 %, R125 25 %, R134a 52 % by mass", or "Mixture: ..." for a blend without a name.

    A named refrigerant blend is shown by mass, as its R number is defined
    (ASHRAE Standard 34); every other mixture in the basis it was given in.
    """
    mass: Optional[Tuple[float, ...]] = None
    if backend == "HEOS":
        mass = fractions if basis == "mass" else _mass_fractions(components, fractions) if basis == "mole" else None
    if mass is not None:
        blend = blend or blend_name(components, mass)
        if re.match(r"R\d", blend):
            fractions, basis = mass, "mass"
    return "{0}: {1}".format(blend or "Mixture", composition_text(components, fractions, basis))


@lru_cache(maxsize=256)
def _fluid_lines(backend: str, components: Tuple[str, ...], fractions: Tuple[float, ...], basis: str, blend: str,
                 style: str) -> Tuple[str, ...]:
    if backend != "HEOS":
        names = ", ".join(components)
        if fractions:
            names = composition_text(components, fractions, basis)
        labels = {"REFPROP": "REFPROP", "PR": "Peng-Robinson equation of state",
                  "SRK": "Soave-Redlich-Kwong equation of state", "INCOMP": "CoolProp incompressible fluid"}
        return ("{0}: {1}".format(names, labels.get(backend, backend + " backend of CoolProp")),)
    lines = []
    if len(components) > 1 and len(fractions) == len(components):
        lines.append(_composition_line(backend, components, fractions, basis, blend))
    for name in components:
        try:
            key = CP.get_BibTeXKey(name, "EOS")
        except Exception:   # an unknown name: nothing to cite
            continue
        # Some fluids name several sources, separated by commas
        sources = [k.strip() for k in key.split(",") if k.strip()]
        lines.append("{0}: {1}".format(name, _join_citations(sources, style)))
    if len(components) > 1:
        keys = []
        for a, b in combinations(components, 2):
            pair = _pair_key(a, b)
            if pair and pair not in keys:
                keys.append(pair)
        if keys:
            lines.append("Mixture model: " + _join_citations(keys, style))
    return tuple(lines)


def _join_citations(keys, style: str) -> str:
    """The citations of several keys, separated by "; ".

    A citation that reads the same as an earlier one is left out: in the
    short style a paper, its erratum and a thesis of the same author and
    year all read "Thol (2015)". The full style tells them apart.
    """
    texts = []
    for key in keys:
        text = cite(key, style)
        if text not in texts:
            texts.append(text)
    return "; ".join(texts)


def versions_line() -> str:
    """"CoolProp 8.1.0dev (83f3ca3), CoolPlot 1.2.0.dev0"; the git revision only for development builds."""
    from ..__version__ import __version__ as coolplot_version
    version = CoolProp.__version__
    if "dev" in version:
        revision = str(getattr(CoolProp, "__gitrevision__", "") or "")[:7]
        if revision:
            version += " ({0})".format(revision)
    return "CoolProp {0}, CoolPlot {1}".format(version, coolplot_version)
