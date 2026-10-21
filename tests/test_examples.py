# -*- coding: utf-8 -*-
"""The examples keep working: run each one and check what it writes."""
import os
import subprocess
import sys

import pytest

pytest.importorskip("CoolProp")
pytest.importorskip("matplotlib")

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")


def _run(name, tmp_path):
    env = dict(os.environ, MPLBACKEND="Agg")
    out = subprocess.run([sys.executable, "-W", "error::UserWarning", os.path.join(EXAMPLES, name)],
                         cwd=tmp_path, env=env, capture_output=True, text=True, timeout=600)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_quickstart(tmp_path):
    assert "COP heating" in _run("quickstart.py", tmp_path)
    assert (tmp_path / "R290_ph.svg").stat().st_size > 10000
    assert (tmp_path / "R290_ph.png").stat().st_size > 10000


def test_two_stage_cycles(tmp_path):
    assert "economizer" in _run("two_stage_cycles.py", tmp_path)
    assert (tmp_path / "two_stage_cycles.png").stat().st_size > 10000


def test_refrigerant_blend(tmp_path):
    _run("refrigerant_blend.py", tmp_path)
    assert (tmp_path / "R32_R125_ph.svg").stat().st_size > 10000


def test_saturation_lines(tmp_path):
    assert "s: through the saturated vapour every 10 K" in _run("saturation_lines.py", tmp_path)
    svg = (tmp_path / "R290_saturation.svg").read_text()
    assert "s=" in svg and "kJ/kg/K" in svg and "T_sat=" not in svg and len(svg) > 10000   # labelled by value


def test_psychrometric(tmp_path):
    assert "RH =" in _run("psychrometric.py", tmp_path)
    assert (tmp_path / "psychrometric.svg").stat().st_size > 10000


def test_psychrometric_processes(tmp_path):
    out = _run("psychrometric_processes.py", tmp_path)
    assert "Desiccant dehumidification" in out
    svg = (tmp_path / "psychrometric_processes.svg").read_text()
    assert "+14.3 kJ/kg" in svg and "Steam humidification" in svg and len(svg) > 10000   # labels and legend


def test_psychrometric_air_handling(tmp_path):
    assert "Cooling coil" in _run("psychrometric_air_handling.py", tmp_path)
    svg = (tmp_path / "psychrometric_air_handling.svg").read_text()
    assert "comfort zone" in svg and "SHR" in svg and "steam" in svg and len(svg) > 10000


def test_psychrometric_evaporative_cooling(tmp_path):
    assert "Indirect, then direct" in _run("psychrometric_evaporative_cooling.py", tmp_path)
    svg = (tmp_path / "psychrometric_evaporative_cooling.svg").read_text()
    assert "outdoor air" in svg and "supply" in svg and len(svg) > 10000


def _ports_installed() -> bool:
    from coolplot import corelib
    from coolplot.thermo import native
    return corelib.available() or native.available()


# Runs an example and writes to scenes.json every scene it composed and how
# often each C++ path really answered, so that the scenes themselves are
# compared (also for an example that saves nothing) and a run that silently
# fell back to Python is caught. The warning filter is set here: a "-W" option
# naming a coolplot class is ignored by Python, which starts before coolplot.
_RECORD_SCENES = """
import atexit, json, runpy, sys, warnings
from coolplot import corelib
from coolplot.chart import Chart
from coolplot.thermo import native
warnings.simplefilter("error", corelib.CoreFallbackWarning)
scenes = []
answered = {"compose": 0, "svg": 0, "numerics": 0}

def counted(module, name, what):
    real = getattr(module, name)
    def call(*args, **kwargs):
        result = real(*args, **kwargs)
        if result is not None:
            answered[what] += 1
        return result
    setattr(module, name, call)

counted(corelib, "compose", "compose")
counted(corelib, "scene_to_svg", "svg")
counted(native, "compute_curve", "numerics")
_update_scene = Chart.update_scene
def update_scene(self, *args, **kwargs):
    scene = _update_scene(self, *args, **kwargs)
    scenes.append(scene.to_dict())
    return scene
Chart.update_scene = update_scene
def dump():
    with open("scenes.json", "w") as f:
        json.dump({"core": corelib.available(), "numerics": native.available(), "answered": answered,
                   "scenes": scenes}, f, allow_nan=False)
atexit.register(dump)
sys.argv = [sys.argv[1]]
runpy.run_path(sys.argv[0], run_name="__main__")
"""


def _same(a, b, path="", rel=1e-9):
    """Plain data compared with numbers within ``rel`` relative; the first difference, or ""."""
    import math
    if isinstance(a, float) or isinstance(b, float):
        ok = isinstance(a, (int, float)) and isinstance(b, (int, float)) and math.isclose(
            a, b, rel_tol=rel, abs_tol=1e-12)
        return "" if ok else "{0}: {1!r} vs {2!r}".format(path, a, b)
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return "{0}: keys differ by {1}".format(path, sorted(set(a) ^ set(b)))
        return next((d for d in (_same(a[k], b[k], path + "." + k, rel) for k in sorted(a)) if d), "")
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return "{0}: {1} vs {2} entries".format(path, len(a), len(b))
        return next((d for d in (_same(x, y, "{0}[{1}]".format(path, i), rel) for i, (x, y) in enumerate(zip(a, b)))
                     if d), "")
    return "" if a == b else "{0}: {1!r} vs {2!r}".format(path, a, b)


#: The examples run in both modes: every script in examples/ (the web_app
#: folder is a server, tested by tests/test_web_server.py).
BOTH_PATHS = ["quickstart.py", "two_stage_cycles.py", "refrigerant_blend.py", "psychrometric.py",
              "interactive_cycle.py", "saturation_lines.py", "psychrometric_processes.py",
              "psychrometric_air_handling.py", "psychrometric_evaporative_cooling.py"]


def test_the_list_of_examples_is_complete():
    assert sorted(BOTH_PATHS) == sorted(f for f in os.listdir(EXAMPLES) if f.endswith(".py"))


def _child_environment(mode: str) -> dict:
    """The environment of an example run: absolute import paths, since the child runs elsewhere."""
    from coolplot import corelib
    paths = [os.path.abspath(p) for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
    if corelib._core is not None:
        paths.insert(0, os.path.dirname(os.path.abspath(corelib._core.__file__)))
    return dict(os.environ, MPLBACKEND="Agg", COOLPLOT_NATIVE=mode, PYTHONPATH=os.pathsep.join(paths))


@pytest.mark.skipif(not _ports_installed(), reason="neither C++ port is installed, both modes run the Python code")
@pytest.mark.parametrize("name", BOTH_PATHS)
def test_every_example_draws_the_same_from_both_paths(name, tmp_path):
    """Plan 0.9: the scene of every example is the same from the Python code and the C++ ports.

    Each example runs with the native mode "off" (Python everywhere) and
    "on" (coolplot-core and CoolProp's port wherever installed). Every
    scene it composes has to agree to 1e-9, and every file it writes, SVG
    and PNG alike, byte for byte. In "on" the installed ports have to have
    answered; a fallback to Python is an error.

    CoolProp's port of the numerics agrees with the Python numerics to the
    rounding of CoolProp's solvers, not bit for bit (tests/test_native.py).
    When it computed lines, the scenes have to agree to 1e-7 and the files
    are compared by name only, since a coordinate written with three
    decimals can round the other way.
    """
    import json
    import re
    from coolplot import corelib
    from coolplot.thermo import native
    outputs = {}
    for mode in ("0", "1"):
        folder = tmp_path / mode
        folder.mkdir()
        out = subprocess.run([sys.executable, "-W", "error::UserWarning", "-c", _RECORD_SCENES,
                              os.path.join(EXAMPLES, name)],
                             cwd=folder, env=_child_environment(mode), capture_output=True, text=True, timeout=600)
        assert out.returncode == 0, out.stderr
        record = json.loads((folder / "scenes.json").read_text())
        # The child sees the same ports as this process
        assert (record["core"], record["numerics"]) == (corelib.available(), native.available()), record
        answered = record["answered"]
        if mode == "0":
            assert answered == {"compose": 0, "svg": 0, "numerics": 0}, answered
        else:
            if record["core"]:
                assert answered["compose"] > 0, answered
            if record["numerics"] and name != "psychrometric.py":   # humid air is not part of the port
                assert answered["numerics"] > 0, answered
        scenes = record["scenes"]
        files = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file() and p.name != "scenes.json"}
        outputs[mode] = (out.stdout, scenes, files, answered["numerics"] > 0)
    (text_off, scenes_off, files_off, _), (text_on, scenes_on, files_on, noisy) = outputs["0"], outputs["1"]
    assert scenes_off, "the example composed no scene"
    difference = _same(scenes_off, scenes_on, "scenes", rel=1e-7 if noisy else 1e-9)
    assert difference == "", difference
    assert sorted(files_on) == sorted(files_off)
    if not noisy:
        for file_name in files_off:
            assert files_on[file_name] == files_off[file_name], file_name

    # The printed text matches too, except for timings such as "drawn in 1.2 s"
    def untimed(text):
        return re.sub(r"\d+(\.\d+)? (s|ms)\b", "<time>", text)
    assert untimed(text_on) == untimed(text_off)
