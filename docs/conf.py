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
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "v1_plan.md", "v1_review.md"]
templates_path = ["_templates"]
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
numpydoc_validation_exclude = {r"\.__init__$", r"\.__getattr__$", r"\.__reduce__$", r"coolplot\.testing\..*",
                               r"\.AbstractState$", r"\.ProcessPoolExecutor$", r"\.ThreadPoolExecutor$"}

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
}

html_theme = "pydata_sphinx_theme"
html_static_path = ["_static"]
html_logo = None
html_title = "CoolPlot {0}".format(__version__)
html_theme_options = {
    "github_url": "https://github.com/CoolProp/CoolPlot",
    "show_toc_level": 2,
    "navigation_with_keys": False,
}
html_context = {"default_mode": "light"}
html_css_files = ["coolplot.css"]


def setup(app):
    """Write the generated reference tables before the sources are read."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _tables
    _tables.write(os.path.join(os.path.dirname(__file__), "reference", "tables.md"))


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
    seen = block_vars.setdefault("_files_seen", set())
    found = []
    for pattern in ("*.svg", "*.png"):
        for path in sorted(glob.glob(os.path.join(example_dir, pattern))):
            if path in seen:
                continue
            seen.add(path)
            target = next(block_vars["image_path_iterator"])
            if path.endswith(".svg"):
                target = target[:-4] + ".svg"
            shutil.copyfile(path, target)
            found.append(target)
    return figure_rst(found, gallery_conf["src_dir"])


sphinx_gallery_conf["image_scrapers"] = ("matplotlib", _files_written)
