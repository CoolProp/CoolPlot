# -*- coding: utf-8 -*-
"""The JavaScript renderer of scene JSON (src/coolplot/render/static/scene_svg.js).

Node runs tests/js/check_scene_svg.js, which compares its SVG with the
golden files the Python writer made (cpp/tests/data); a browser test draws a
server-free page. Both skip when Node or Playwright is missing.
"""
import os
import shutil
import subprocess

import pytest

from coolplot.render.svg import SvgRenderer
from coolplot.render.web import scene_page, scene_script
from coolplot.testing import conformance_scene

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_the_script_is_ascii_and_packaged():
    text = scene_script()
    text.encode("ascii")
    assert "toSvg" in text


def test_node_writes_the_golden_svg_files():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = os.path.join(ROOT, "tests", "js", "check_scene_svg.js")
    out = subprocess.run([node, script], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr


def _node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    return node


def test_node_formats_numbers_as_python_does():
    """num and formatNumber against Python, with exact ties, huge values and noise."""
    import json
    import random
    from coolplot.core.numbers import format_number
    from coolplot.render.svg import _num
    rng = random.Random(7)
    values = [0.0625, -0.0625, 0.0005, 2.5, -2.5, 0.125, 1.5, 0.5, 1e21, -3e22, 1.7976931348623157e308,
              0.30000000000000004, 1e-300, 123456.5, 9.9995, 0.00025, 1e6, 999999.5]
    values += [rng.uniform(-1e4, 1e4) for _ in range(300)]
    values += [rng.randint(-4000, 4000) / 16.0 for _ in range(200)]   # many exact ties
    values += [rng.randint(-99, 99) / 8.0 * 10.0 ** rng.randint(-8, 8) for _ in range(200)]
    expected = {"num": [_num(v) for v in values],
                "format": [[format_number(v, d) for d in (1, 2, 3, 6)] for v in values]}
    library = os.path.join(ROOT, "src", "coolplot", "render", "static", "scene_svg.js")
    script = ("var lib = require(" + json.dumps(library) + ");"
              "var values = " + json.dumps(values) + ";"
              "console.log(JSON.stringify({num: values.map(lib.num), format: values.map(function (v) {"
              "return [1, 2, 3, 6].map(function (d) { return lib.formatNumber(v, d); }); })}));")
    out = subprocess.run([_node(), "-e", script], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    made = json.loads(out.stdout)
    for key in ("num", "format"):
        wrong = [(v, a, b) for v, a, b in zip(values, made[key], expected[key]) if a != b]
        assert not wrong, (key, wrong[:5])


def test_the_page_holds_the_scene_safely():
    scene = conformance_scene()
    page = scene_page(scene, title="A <chart>")
    page.encode("ascii")
    assert "<title>A &lt;chart&gt;</title>" in page
    # A text with "</script>" in it cannot end the scene's script element early
    from dataclasses import replace
    scene.put(replace(scene["text/plain"], text="</script><b>"))
    page = scene_page(scene)
    assert page.count("</script>") == 3 and "<b>" not in page and "<!--" not in page
    # The scene is written in scene order (not drawing order), so the legend
    # comes out as in the SVG backend
    positions = [page.index('"id":"{0}"'.format(i)) for i in scene.ids()]
    assert positions == sorted(positions) and scene.ids() != scene.draw_order()


@pytest.mark.browser
def test_a_browser_draws_the_page_as_the_svg_backend_writes(tmp_path, browser):
    scene = conformance_scene()
    renderer = SvgRenderer(native=False)
    renderer.sync(scene)
    path = tmp_path / "page.html"
    path.write_text(scene_page(scene), encoding="ascii")
    page = browser.new_page()
    try:
        page.goto(path.as_uri())
        markup = page.evaluate("document.querySelector('#coolplot-root svg').outerHTML")
    finally:
        page.close()
    # The browser parsed exactly the document the SVG backend writes: same items, same order
    import xml.etree.ElementTree as ET
    drawn = [g.get("data-item") for g in ET.fromstring(markup).iter() if g.get("data-item") is not None]
    written = [g.get("data-item") for g in ET.fromstring(renderer.to_svg()).iter() if g.get("data-item") is not None]
    assert drawn == written and len(drawn) > 10
