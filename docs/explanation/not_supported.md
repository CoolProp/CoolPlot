# What is not supported

* **Diagram types** other than p-h, T-s, h-s, p-s, p-rho, T-rho and p-T
  for fluids and the T-W (ASHRAE) psychrometric chart. A Mollier h-x
  chart of humid air is planned as a variant of the same model.
* **Lines of constant specific volume** of a fluid: v is a state
  quantity (1/rho) but not a line family; use density.
* **Property calculations other than CoolProp's**: the fluids, the
  mixture models and their limits are CoolProp's. REFPROP works through
  CoolProp where it is installed.
* **Incompressible fluids** have no saturation curve: no dome, no quality
  lines, and the limits have to be given absolute.
* **CoolProp 6 and 7**: the mixture flashes CoolPlot relies on exist in
  CoolProp 8 only.
* **CMYK colour and colour profiles** in PDF: output is sRGB.
* **The plotly backend** cannot set line caps and always draws texts
  above lines; everything else looks the same as in matplotlib.
* **Fonts installed as CFF OpenType** cannot be embedded in PDF as
  TrueType by matplotlib; the next font of the list is used in the file.
* **Interactive charts in plotly**: zoom and hover come from plotly
  itself; dragging cycle states works in matplotlib and in the browser
  backend.
