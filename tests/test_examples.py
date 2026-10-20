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
