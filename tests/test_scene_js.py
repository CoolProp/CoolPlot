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


def test_the_page_holds_the_scene_safely():
    scene = conformance_scene()
    page = scene_page(scene, title="A <chart>")
    page.encode("ascii")
    assert "<title>A &lt;chart&gt;</title>" in page
    # A text with "</script>" in it cannot end the scene's script element early
    from dataclasses import replace
    scene.put(replace(scene["text/plain"], text="</script><b>"))
    page = scene_page(scene)
    assert page.count("</script>") == 3


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
