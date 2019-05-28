
![GitHub License](https://img.shields.io/github/license/coolprop/coolplot.svg)
![Coverage - Codecov](https://img.shields.io/codecov/c/gh/CoolProp/CoolPlot.svg)
![Coverage - Coveralls](https://img.shields.io/coveralls/github/CoolProp/CoolPlot.svg)
![PyPI - Version](https://img.shields.io/pypi/v/coolplot.svg)
![PyPI - Downloads](https://img.shields.io/pypi/dm/coolplot.svg)


CoolPlot
========

This repository contain code for a Python module to create property plots
for engineering thermodynamics applications using [CoolProp].

It focusses on refrigeration and heat pumping applications and the enthalpy-
pressure diagrams (logp,h) are considered to be more mature than others.
However, entropy-temperature diagrams (T,s) have also been implemented and
should work for most fluids.

We are still in the process of separating the calculations from the plotting
routines - expect some breaking changes until v1.0.0 is released. The code
has been forked from the main [CoolProp repository] at v6.3.0 and the history
was preserved, thus the old commits.

Pull requests are encouraged!


Installation
------------

The project gets published on [PyPi] as `coolplot` and you can install it
using pip

```bash
pip install coolplot
```


License
-------

This Python package is released under the terms of the MIT license. 


  [CoolProp]: http://coolprop.sourceforge.net/
  [CoolProp repository]: https://github.com/CoolProp/CoolProp
  [PyPi]: https://docs.python.org/3/distutils/packageindex.html
