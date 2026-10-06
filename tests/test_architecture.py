# -*- coding: utf-8 -*-
"""Guard the layering described in docs/architecture.md.

Each check runs in a fresh interpreter, because a module that is already
imported by another test would hide a forbidden import.
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _loaded_after(import_stmt):
    code = ("import sys\n{0}\n"
            "print(','.join(sorted(m.split('.')[0] for m in sys.modules)))").format(import_stmt)
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    return set(out.stdout.strip().split(","))


@pytest.mark.parametrize("module", ["CoolPlot.quantities", "CoolPlot.units", "CoolPlot.scene",
                                    "CoolPlot.style", "CoolPlot.render.base", "CoolPlot.render.svg"])
def test_pure_modules_need_neither_coolprop_nor_matplotlib(module):
    loaded = _loaded_after("import " + module)
    assert "CoolProp" not in loaded
    assert "matplotlib" not in loaded


@pytest.mark.parametrize("module", ["CoolPlot.thermo", "CoolPlot.diagram"])
def test_calculation_layers_do_not_import_matplotlib(module):
    loaded = _loaded_after("import " + module)
    assert "matplotlib" not in loaded


def test_building_a_scene_does_not_import_matplotlib():
    loaded = _loaded_after(
        "from CoolPlot import PropertyDiagram\n"
        "from CoolPlot.render.svg import SvgRenderer\n"
        "d = PropertyDiagram('R290', 'ph', tp_limits='ACHP')\n"
        "d.set_isolines('Q', num=3)\n"
        "SvgRenderer().sync(d.update_scene())")
    assert "matplotlib" not in loaded
