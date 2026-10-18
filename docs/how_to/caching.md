# Keep traced lines between runs

A chart remembers every line it traced: zooming, panning, changing the
units, the theme, the labels or a cycle traces nothing again, and adding
a family traces only its new lines. That memory ends with the program.
To keep the lines on disk, so that the next run, a restarted notebook or
a second process finds them, give the chart a cache with a folder:

```python
from coolplot import PropertyDiagram
from coolplot.engine import CurveCache

diagram = PropertyDiagram("HEOS::R407C.mix", "ph", cache=CurveCache(directory=True))
```

`directory=True` uses `~/.CoolProp/CoolPlot/Curves`, next to the tables
CoolProp keeps for its TTSE and BICUBIC backends. A path uses that
folder. Setting the environment variable `COOLPLOT_CACHE_DIR` to a folder
switches it on for every chart without changing the code. Without either,
nothing is written: a script that draws one chart gains nothing from it.

How the folder is kept follows CoolProp's own table cache:

* one folder per fluid and composition, named like CoolProp's, for
  example `HEOS(R32[0.7000000000]&R125[0.3000000000])`;
* one compressed file per line, named by a digest of everything the line
  depends on, CoolProp's version, configuration and reference state
  included, so a changed CoolProp never serves old lines;
* a file of an older format, or one that cannot be read, is traced again
  and replaced;
* the folder moves with CoolProp's `ALTERNATIVE_TABLES_DIRECTORY` and
  obeys CoolProp's `MAXIMUM_TABLE_DIRECTORY_SIZE_IN_GB`: above it a
  warning, above 1.5 times it no more lines are written (the chart still
  draws).

Several processes may share the folder: files are written whole or not
at all. To start over, delete the folder.

A traced line belongs to one diagram type: the p-h and the T-s chart of
the same fluid trace their isotherms separately, because a line is
stepped by its shape on the page.
