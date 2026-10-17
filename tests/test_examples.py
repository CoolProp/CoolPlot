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


def test_psychrometric(tmp_path):
    assert "RH =" in _run("psychrometric.py", tmp_path)
    assert (tmp_path / "psychrometric.svg").stat().st_size > 10000


def _ports_installed() -> bool:
    from coolplot import corelib
    from coolplot.thermo import native
    return corelib.available() or native.available()


# Runs an example and writes every scene it composed to scenes.json, so that
# the scenes themselves are compared, also for an example that saves nothing
_RECORD_SCENES = """
import atexit, json, runpy, sys
from coolplot.chart import Chart
scenes = []
_update_scene = Chart.update_scene
def update_scene(self, *args, **kwargs):
    scene = _update_scene(self, *args, **kwargs)
    scenes.append(scene.to_dict())
    return scene
Chart.update_scene = update_scene
def dump():
    from coolplot import corelib
    from coolplot.thermo import native
    with open("scenes.json", "w") as f:
        json.dump({"core": corelib.enabled(), "numerics": native.enabled(), "scenes": scenes}, f, allow_nan=False)
atexit.register(dump)
sys.argv = [sys.argv[1]]
runpy.run_path(sys.argv[0], run_name="__main__")
"""


def _same(a, b, path=""):
    """Plain data compared with numbers within 1e-9 relative; the first difference, or ""."""
    import math
    if isinstance(a, float) or isinstance(b, float):
        ok = isinstance(a, (int, float)) and isinstance(b, (int, float)) and math.isclose(
            a, b, rel_tol=1e-9, abs_tol=1e-12)
        return "" if ok else "{0}: {1!r} vs {2!r}".format(path, a, b)
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return "{0}: keys differ by {1}".format(path, sorted(set(a) ^ set(b)))
        return next((d for d in (_same(a[k], b[k], path + "." + k) for k in sorted(a)) if d), "")
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return "{0}: {1} vs {2} entries".format(path, len(a), len(b))
        return next((d for d in (_same(x, y, "{0}[{1}]".format(path, i)) for i, (x, y) in enumerate(zip(a, b))) if d),
                    "")
    return "" if a == b else "{0}: {1!r} vs {2!r}".format(path, a, b)


@pytest.mark.skipif(not _ports_installed(), reason="neither C++ port is installed, both modes run the Python code")
@pytest.mark.parametrize("name", ["quickstart.py", "two_stage_cycles.py", "refrigerant_blend.py", "psychrometric.py",
                                  "interactive_cycle.py"])
def test_every_example_draws_the_same_from_both_paths(name, tmp_path):
    """Plan 0.9: the scene of every example is the same from the Python code and the C++ ports.

    Each example runs with the native mode "off" (Python everywhere) and
    "on" (coolplot-core and CoolProp's port wherever installed). Every
    scene it composes has to agree to 1e-9, and every file it writes, SVG
    and PNG alike, byte for byte.
    """
    import json
    import re
    outputs = {}
    for mode in ("0", "1"):
        folder = tmp_path / mode
        folder.mkdir()
        env = dict(os.environ, MPLBACKEND="Agg", COOLPLOT_NATIVE=mode)
        out = subprocess.run([sys.executable, "-W", "error::UserWarning", "-W",
                              "error::coolplot.corelib.CoreFallbackWarning", "-c", _RECORD_SCENES,
                              os.path.join(EXAMPLES, name)],
                             cwd=folder, env=env, capture_output=True, text=True, timeout=600)
        assert out.returncode == 0, out.stderr
        record = json.loads((folder / "scenes.json").read_text())
        # Mode "0" runs Python only; mode "1" really goes through a port
        assert (record["core"] or record["numerics"]) == (mode == "1"), record.keys()
        scenes = record["scenes"]
        files = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file() and p.name != "scenes.json"}
        outputs[mode] = (out.stdout, scenes, files)
    (text_off, scenes_off, files_off), (text_on, scenes_on, files_on) = outputs["0"], outputs["1"]
    assert scenes_off, "the example composed no scene"
    difference = _same(scenes_off, scenes_on, "scenes")
    assert difference == "", difference
    assert sorted(files_on) == sorted(files_off)
    for file_name in files_off:
        assert files_on[file_name] == files_off[file_name], file_name

    # The printed text matches too, except for timings such as "drawn in 1.2 s"
    def untimed(text):
        return re.sub(r"\d+(\.\d+)? (s|ms)\b", "<time>", text)
    assert untimed(text_on) == untimed(text_off)
