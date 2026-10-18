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
CoolProp keeps for its TTSE and BICUBIC backends, or the folder the
environment variable `COOLPLOT_CACHE_DIR` names. A path uses that folder.
Setting `COOLPLOT_CACHE_DIR` switches the cache on for every chart
without changing the code (`0`, `off` or an empty value switch it off).
Without either, nothing is written: a script that draws one chart gains
nothing from it.

How the folder is kept follows CoolProp's own table cache:

* one folder per fluid and composition, named after CoolProp's, for
  example `HEOS(R32[0.7000000000]&R125[0.3000000000])` (a pure fluid has
  no fraction: `HEOS(R290)`);
* one compressed file per line, named by a digest of everything the line
  depends on: the chart's inputs for that line, CoolProp's version, git
  revision, configuration and reference state, and CoolPlot's version. A
  different CoolProp build or CoolPlot release traces its lines again;
* a file of an older format, of another key, or one that cannot be read
  is traced again and replaced;
* the folder sits inside CoolProp's `ALTERNATIVE_TABLES_DIRECTORY` when
  that is set, and obeys CoolProp's `MAXIMUM_TABLE_DIRECTORY_SIZE_IN_GB`
  for the whole folder of lines: above it a warning, above 1.5 times it
  no more lines are written (the chart still draws). The size is counted
  roughly: what the folder held at the first write, plus this process's
  own writes.

With a disk cache the engine checks once per update whether
`CoolProp.CoolProp.set_reference_state` moved the fluid's enthalpy and
entropy, and starts afresh if it did, so lines of one reference state are
never stored under another.

Several processes may share the folder: files are written whole or not
at all, and a file another process holds open is simply skipped. To start
over, delete the folder.

What the key cannot see: the version of a REFPROP library behind a
`REFPROP::` fluid, and binary interaction parameters changed globally
with `set_mixture_binary_pair_data`. After changing either, use a new
folder or delete the old one.

A traced line belongs to one diagram type: the p-h and the T-s chart of
the same fluid trace their isotherms separately, because a line is
stepped by its shape on the page.
