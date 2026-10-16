# -*- coding: utf-8 -*-
"""Guard the layering described in docs/architecture.md.

The imports of every module are read statically with ``ast``, including
imports inside functions, so a lazy import cannot slip past the rules. A
runtime check confirms that building and rendering a scene through the
SVG backend does not load matplotlib.
"""
import ast
import os
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
PACKAGE = os.path.join(SRC, "coolplot")

# Layers in order (docs/architecture.md, section 4). A module may import
# layers listed before its own, never the ones after it.
LIBS = {"CoolProp", "matplotlib", "plotly"}
ALL_LAYERS = ["coolplot.core", "coolplot.style", "coolplot.scene", "coolplot.spec", "coolplot.thermo",
              "coolplot.engine", "coolplot.compose", "coolplot.render", "coolplot.diagram",
              "coolplot.psychrometric", "coolplot.export", "coolplot.interaction"]


def _after(layer):
    return set(ALL_LAYERS[ALL_LAYERS.index(layer) + 1:])


# Module -> names it must never import (directly or lazily).
RULES = {
    "coolplot": LIBS,   # the package entry point only loads names on demand
    "coolplot.core": LIBS | _after("coolplot.core"),
    "coolplot.style": LIBS | _after("coolplot.style"),
    "coolplot.style.values": LIBS | _after("coolplot.style") | {"coolplot.style.theme"},
    "coolplot.scene": LIBS | _after("coolplot.scene") | {"coolplot.style.theme"},
    # Specs are plain data: no CoolProp, and themes are the only style part they hold.
    "coolplot.spec": LIBS | {"coolplot.scene"} | _after("coolplot.spec"),
    "coolplot.thermo": {"matplotlib", "coolplot.style", "coolplot.scene", "coolplot.spec"}
                       | _after("coolplot.thermo"),
    "coolplot.engine": {"matplotlib", "coolplot.style", "coolplot.scene"} | _after("coolplot.engine"),
    # Composing a scene uses no property calculations and no plotting library.
    "coolplot.compose": LIBS | {"coolplot.thermo", "coolplot.engine"} | _after("coolplot.compose"),
    # Backends see only the scene and style values; themes are resolved before.
    "coolplot.render": LIBS | {"coolplot.spec", "coolplot.thermo", "coolplot.engine", "coolplot.compose",
                               "coolplot.diagram", "coolplot.psychrometric", "coolplot.interaction", "coolplot.style.theme",
                               "coolplot.render.mpl", "coolplot.render.svg"},
    "coolplot.render.base": LIBS | {"coolplot.spec", "coolplot.thermo", "coolplot.engine", "coolplot.compose",
                                    "coolplot.diagram", "coolplot.psychrometric", "coolplot.interaction", "coolplot.style.theme"},
    "coolplot.render.svg": LIBS | {"coolplot.spec", "coolplot.thermo", "coolplot.engine", "coolplot.compose",
                                   "coolplot.diagram", "coolplot.psychrometric", "coolplot.interaction", "coolplot.style.theme"},
    "coolplot.render.testing": LIBS | {"coolplot.spec", "coolplot.thermo", "coolplot.engine",
                                       "coolplot.compose", "coolplot.diagram", "coolplot.psychrometric", "coolplot.interaction", "coolplot.style.theme",
                                       "coolplot.render.mpl", "coolplot.render.plotly"},
    # The web backend builds on the SVG backend's elements
    "coolplot.render.web": LIBS | {"coolplot.spec", "coolplot.thermo", "coolplot.engine", "coolplot.compose",
                                   "coolplot.diagram", "coolplot.psychrometric", "coolplot.interaction", "coolplot.style.theme",
                                   "coolplot.render.mpl", "coolplot.render.plotly"},
    "coolplot.render.plotly": {"CoolProp", "matplotlib", "coolplot.spec", "coolplot.thermo", "coolplot.engine",
                               "coolplot.compose", "coolplot.diagram", "coolplot.interaction",
                               "coolplot.style.theme", "coolplot.render.mpl", "coolplot.render.svg"},
    "coolplot.render.mpl": {"CoolProp", "plotly", "coolplot.spec", "coolplot.thermo", "coolplot.engine",
                            "coolplot.compose", "coolplot.diagram", "coolplot.psychrometric", "coolplot.interaction", "coolplot.style.theme"},
    "coolplot.diagram": {"matplotlib", "coolplot.render", "coolplot.interaction"},
    "coolplot.psychrometric": {"matplotlib", "plotly", "coolplot.render", "coolplot.interaction",
                               "coolplot.diagram"},
    # Writing several charts into one file uses the matplotlib backend only.
    "coolplot.export": {"CoolProp", "plotly", "coolplot.interaction", "coolplot.render.svg",
                        "coolplot.render.plotly", "coolplot.render.web"},
    # The interaction helper works with any backend through the Renderer API.
    "coolplot.interaction": LIBS | {"coolplot.render.mpl", "coolplot.render.svg", "coolplot.thermo",
                                    "coolplot.engine"},
}

# Deliberate, documented exceptions: (module, imported name, reason)
ALLOWED = {
    ("coolplot.diagram", "coolplot.render.mpl"):
        "PropertyDiagram.draw/show/savefig create a MatplotlibRenderer on demand for scripts",
    ("coolplot.psychrometric", "coolplot.render.mpl"):
        "PsychrometricChart.draw/show/savefig create a MatplotlibRenderer on demand for scripts",
}


def _module_name(path):
    rel = os.path.relpath(path, SRC)[:-3].replace(os.sep, ".")
    return rel[:-9] if rel.endswith(".__init__") else rel


def _imports(path):
    """Absolute names of everything a module imports, anywhere in the file."""
    module = _module_name(path)
    package = module if path.endswith("__init__.py") else module.rsplit(".", 1)[0]
    found = set()
    for node in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[:len(base) - node.level + 1]
                prefix = ".".join(base + ([node.module] if node.module else []))
            else:
                prefix = node.module
            found.add(prefix)
            found.update(prefix + "." + alias.name for alias in node.names)
    return found


def _files():
    for folder, _, names in os.walk(PACKAGE):
        for name in names:
            if name.endswith(".py"):
                yield os.path.join(folder, name)


def _rule_for(module):
    best = None
    for prefix in RULES:
        if prefix == "coolplot" and module != "coolplot":
            continue   # the entry-point rule applies to __init__ only
        if module == prefix or module.startswith(prefix + "."):
            if best is None or len(prefix) > len(best):
                best = prefix
    return best


def test_import_rules():
    violations = []
    checked = set()
    for path in _files():
        module = _module_name(path)
        rule = _rule_for(module)
        if rule is None:
            continue
        checked.add(rule)
        for name in _imports(path):
            for forbidden in RULES[rule]:
                if name == forbidden or name.startswith(forbidden + "."):
                    allowed = any(rule == r and (name == n or name.startswith(n + "."))
                                  for r, n in ALLOWED)
                    if not allowed:
                        violations.append("{0} imports {1}".format(module, name))
    assert violations == []
    assert checked == set(RULES)  # every rule matched a real module


def test_the_scanner_sees_lazy_imports():
    path = os.path.join(PACKAGE, "diagram.py")
    assert "coolplot.render.mpl.MatplotlibRenderer" in _imports(path)


def test_building_and_rendering_svg_does_not_load_matplotlib():
    pytest.importorskip("CoolProp")
    code = ("import sys\n"
            "from coolplot import PropertyDiagram\n"
            "from coolplot.render.svg import SvgRenderer\n"
            "d = PropertyDiagram('R290', 'ph', tp_limits='ACHP')\n"
            "d.set_isolines('Q', num=3)\n"
            "r = SvgRenderer(); r.sync(d.update_scene()); r.to_svg()\n"
            "print('matplotlib' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
