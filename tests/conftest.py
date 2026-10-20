# -*- coding: utf-8 -*-
"""Test setup shared by all test modules.

Tests that need a browser (Playwright's Chromium) or Kaleido (plotly
images) are marked ``browser`` and ``kaleido`` and run only with
``--run-browser`` and ``--run-kaleido``; they take most of the suite's
time and need software the library does not depend on.
"""
import glob
import os

import pytest

# Kaleido (plotly images and PDF) needs Chrome. Where Playwright's browsers
# are installed, use its headless shell: it prints PDF reliably, where full
# Chrome now and then refuses ("Printing is not available").
_shells = sorted(glob.glob("/opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell"))
if _shells:
    os.environ.setdefault("BROWSER_PATH", _shells[-1])


def pytest_addoption(parser):
    parser.addoption("--run-browser", action="store_true", default=False,
                     help="run the tests that drive a real browser through Playwright")
    parser.addoption("--run-kaleido", action="store_true", default=False,
                     help="run the tests that write plotly images and PDF through Kaleido")


def pytest_collection_modifyitems(config, items):
    for marker, option in (("browser", "--run-browser"), ("kaleido", "--run-kaleido")):
        if config.getoption(option):
            continue
        skip = pytest.mark.skip(reason="needs {0}; run with {1}".format(marker, option))
        for item in items:
            if marker in item.keywords:
                item.add_marker(skip)


def chromium_path():
    """Playwright's Chromium, or skip the test.

    First where Playwright itself installed it; then the newest one under
    /opt/pw-browsers, for a Playwright package of another version than the
    browsers installed there."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        exe = p.chromium.executable_path
    if exe and os.path.isfile(exe):
        return exe
    found = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    if not found:
        pytest.skip("no Chromium for Playwright")
    return found[-1]


@pytest.fixture(scope="module")
def browser():
    """A headless Chromium through Playwright, shared by the tests of one module."""
    exe = chromium_path()   # skips first when Playwright or Chromium is missing
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe)
        yield b
        b.close()
