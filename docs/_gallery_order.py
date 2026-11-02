"""Order of the examples in the gallery.

Read by sphinx-gallery through conf.py. The examples are sorted by file
name, except the company chart (branding_chp.py), which comes last: it
shows how to brand a chart, not what CoolPlot can draw.
"""

LAST = ("branding_chp.py",)


def company_chart_last(filename):
    """Sort key: file name, with the files in LAST at the end."""
    return (filename in LAST, filename)
