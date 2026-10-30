# -*- coding: utf-8 -*-
"""Sphinx configuration of the CoolPlot documentation.

Markdown (MyST) pages, numpydoc docstrings, the API reference generated
by autosummary, and the gallery built from ``examples/`` by
sphinx-gallery, which runs every example. ``sphinx-build -W`` (warnings
are errors) is what CI runs.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from coolplot import __version__  # noqa: E402

project = "CoolPlot"
author = "The CoolProp developers"
copyright = "2014-2026, the CoolProp developers"
version = release = __version__

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "numpydoc",
    "sphinx_gallery.gen_gallery",
]

source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
master_doc = "index"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
# The gallery configuration holds a function (the scraper below), which
# Sphinx cannot cache between builds; that is a notice, not a problem
suppress_warnings = ["config.cache"]

# MyST: tables, definition lists, admonitions and $math$
myst_enable_extensions = ["colon_fence", "deflist", "dollarmath", "fieldlist"]
myst_heading_anchors = 3

# API reference: one page per module, generated into reference/generated
autosummary_generate = True
autosummary_imported_members = False
autodoc_default_options = {"members": True, "undoc-members": False, "show-inheritance": True}
autodoc_member_order = "bysource"
autodoc_typehints = "none"   # numpydoc writes the types in the Parameters sections
numpydoc_show_class_members = False
numpydoc_class_members_toctree = False
# Docstrings are checked at build time; a failing check is a warning,
# which -W turns into a build error. GL08: a public object without a
# docstring. The section checks (parameters, returns) are not enforced:
# the docstrings describe what matters in prose.
numpydoc_validation_checks = {"GL08"}
# Chart.kind is a class attribute set to None (documented with a "#:"
# comment); before Python 3.13 None has no docstring of its own, so the
# check would report it there and pass on newer Pythons.
numpydoc_validation_exclude = {r"\.__init__$", r"\.__getattr__$", r"\.__reduce__$", r"coolplot\.testing\..*",
                               r"\.AbstractState$", r"\.ProcessPoolExecutor$", r"\.ThreadPoolExecutor$",
                               r"coolplot\.chart\.Chart\.kind$"}

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable", None),
    "matplotlib": ("https://matplotlib.org/stable", None),
}
intersphinx_timeout = 10

# The gallery: every example in examples/ is run at build time and shown
# with its output. The web application is left out (it starts a server).
sphinx_gallery_conf = {
    "examples_dirs": "../examples",
    "gallery_dirs": "gallery",
    "filename_pattern": r".*\.py",
    "ignore_pattern": r"web_app|__init__",
    "download_all_examples": False,
    "remove_config_comments": True,
    "matplotlib_animations": False,
    "plot_gallery": "True",
    "reset_modules": ("matplotlib",),
    "within_subsection_order": "FileNameSortKey",
    "min_reported_time": 1,
    "show_memory": False,
    # Needed by the minigallery on the landing page (a few thumbnails that
    # link to their examples); the files written there are not pages
    "backreferences_dir": "gallery/backreferences",
}

html_theme = "pydata_sphinx_theme"
html_static_path = ["_static"]
html_logo = None
html_title = "CoolPlot {0}".format(__version__)
html_theme_options = {
    "github_url": "https://github.com/CoolProp/CoolPlot",
    "show_toc_level": 2,
    # The top bar shows the pages of the main toctree in its order, the first
    # six as links (from Getting started to Reference), the rest under "More"
    "header_links_before_dropdown": 6,
    "navigation_with_keys": False,
}
html_context = {"default_mode": "light"}
html_css_files = ["coolplot.css"]


def setup(app):
    """Write the generated reference tables, and clear the examples' old output files."""
    import glob
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _tables
    _tables.write(os.path.join(os.path.dirname(__file__), "reference", "tables.md"))
    examples = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "examples")
    for pattern in ("*.svg", "*.png", "*.pdf", "*.html"):
        for path in glob.glob(os.path.join(examples, pattern)):
            os.remove(path)   # a file of an earlier run must not be shown as this run's output


def _files_written(block, block_vars, gallery_conf):
    """Gallery scraper: pick up the SVG and PNG files an example writes.

    Several examples draw with the SVG writer and save files instead of
    opening a matplotlib figure; sphinx-gallery only captures figures,
    so the files written since the previous code block are copied next
    to the example's images and shown like figures.
    """
    import glob
    import shutil
    from sphinx_gallery.scrapers import figure_rst
    example_dir = os.path.dirname(block_vars["src_file"])
    found = []
    for pattern in ("*.svg", "*.png"):
        for path in sorted(glob.glob(os.path.join(example_dir, pattern))):
            # A file is claimed once, by the block after which it appeared
            # (or was rewritten); files other examples wrote are claimed
            # already, and setup() removes files of earlier builds
            stamp = (path, os.stat(path).st_mtime_ns)
            if stamp in _CLAIMED_FILES:
                continue
            _CLAIMED_FILES.add(stamp)
            target = next(block_vars["image_path_iterator"])
            if path.endswith(".svg"):
                target = target[:-4] + ".svg"
            shutil.copyfile(path, target)
            found.append(target)
    return figure_rst(found, gallery_conf["src_dir"])


_CLAIMED_FILES = set()
sphinx_gallery_conf["image_scrapers"] = ("matplotlib", _files_written)
