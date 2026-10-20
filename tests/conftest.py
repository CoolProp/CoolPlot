# -*- coding: utf-8 -*-
"""Test setup shared by all test modules."""
import glob
import os

# Kaleido (plotly images and PDF) needs Chrome. Where Playwright's browsers
# are installed, use its headless shell: it prints PDF reliably, where full
# Chrome now and then refuses ("Printing is not available").
_shells = sorted(glob.glob("/opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell"))
if _shells:
    os.environ.setdefault("BROWSER_PATH", _shells[-1])
