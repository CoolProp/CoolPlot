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
PACKAGE = os.path.join(ROOT, "CoolPlot")

# Module -> top-level names it must never import (directly or lazily).
PURE = {"CoolProp", "matplotlib", "CoolPlot.thermo", "CoolPlot.diagram"}
RULES = {
    "CoolPlot.quantities": PURE | {"CoolPlot.scene", "CoolPlot.render"},
    "CoolPlot.units": PURE | {"CoolPlot.scene", "CoolPlot.render"},
    "CoolPlot.style": PURE | {"CoolPlot.scene", "CoolPlot.render", "CoolPlot.theme"},
    "CoolPlot.theme": PURE | {"CoolPlot.scene", "CoolPlot.render"},
    "CoolPlot.scene": PURE | {"CoolPlot.render", "CoolPlot.theme"},
    # The render package itself never imports a backend; users pick one.
    "CoolPlot.render": PURE | {"CoolPlot.theme", "CoolPlot.render.mpl", "CoolPlot.render.svg"},
    "CoolPlot.render.base": PURE | {"CoolPlot.theme"},
    "CoolPlot.render.svg": PURE | {"CoolPlot.theme"},
    "CoolPlot.render.testing": PURE | {"CoolPlot.theme", "CoolPlot.render.mpl"},
    "CoolPlot.render.mpl": {"CoolProp", "CoolPlot.thermo", "CoolPlot.diagram", "CoolPlot.theme"},
    "CoolPlot.thermo": {"matplotlib", "CoolPlot.scene", "CoolPlot.render", "CoolPlot.diagram",
                        "CoolPlot.style", "CoolPlot.theme"},
    "CoolPlot.diagram": {"matplotlib", "CoolPlot.render"},
}

# Deliberate, documented exceptions: (module, imported name, reason)
ALLOWED = {
    ("CoolPlot.diagram", "CoolPlot.render.mpl"):
        "PropertyDiagram.draw/show/savefig create a MatplotlibRenderer on demand for scripts",
}


def _module_name(path):
    rel = os.path.relpath(path, ROOT)[:-3].replace(os.sep, ".")
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
    assert "CoolPlot.render.mpl.MatplotlibRenderer" in _imports(path)


def test_building_and_rendering_svg_does_not_load_matplotlib():
    pytest.importorskip("CoolProp")
    code = ("import sys\n"
            "from CoolPlot import PropertyDiagram\n"
            "from CoolPlot.render.svg import SvgRenderer\n"
            "d = PropertyDiagram('R290', 'ph', tp_limits='ACHP')\n"
            "d.set_isolines('Q', num=3)\n"
            "r = SvgRenderer(); r.sync(d.update_scene()); r.to_svg()\n"
            "print('matplotlib' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
