# Troubleshooting

The messages CoolPlot gives, and what to do.

**`PropertyError: State 1 of the cycle 'hp': no state of HEOS::R290 at p = 60 bar, Q = 0 (p is above the critical pressure 42.5117 bar, where there is no two-phase region to give a quality in; CoolProp: ...)`**
: A state of a cycle cannot be computed. The message names the state,
  the fluid, the inputs in the chart's units, what is wrong where
  CoolPlot can tell (a temperature or pressure outside the equation of
  state, a quality above the critical point, an input pair CoolProp does
  not solve for mixtures), and CoolProp's own words. Fix the inputs; for
  a mixture give p with the other quantity.

**`UserWarning: Skipping the line T=1000 in R290: CoolProp failed for 150 of 150 points`**
: No point of the line could be computed, usually a value outside the
  equation of state. The line is left out; each line warns once. The
  value in the message is in SI units (K, Pa, J/kg).

**`UserWarning: The line s=1500 in R410A.mix has gaps: CoolProp failed for 20 of 190 points inside the line`**
: CoolProp could not compute some points inside the line; they are drawn
  as gaps, never invented. Blends near the critical point are the usual
  case.

**`UserWarning: The line ... is incomplete: the evaluation budget of 2100 points is used up`**
: The line bends so much that the stepping ran out of its budget; the
  drawn part is right. Fewer points (`Settings.calc.points`) or a smaller
  region help.

**`ValueError: INCOMP::MEG[0.3] has no two-phase region ...` or `... has no saturation curve ...; give absolute temperature and pressure limits`**
: An incompressible fluid was given relative limits (the default) or
  asked for quality lines; the second message comes when the chart is
  drawn. Give `tp_limits=[T_min_K, T_max_K, p_min_Pa, p_max_Pa]` and
  leave quality lines out.

**`ValueError: A state has unknown properties ['foo'], expected two of ['T', 'p', 'h', 's', 'rho', 'v', 'u', 'Q']`**
: A state of a cycle names a quantity the chart does not know. The keys
  are those listed for fluids, and T, W, RH, Twb, Tdp, h, v for humid
  air; `"x"` is accepted as an alias of `"Q"`, `"P"` of `"p"`.

**`UserWarning: Inter is installed here only as CFF OpenType, which matplotlib cannot embed as TrueType ...`**
: A font of the theme cannot go into a PDF as TrueType and the next font
  of its list is used in the file. See {doc}`pdf_print`.

**`AttributeError: PropertyDiagram.set_process() was removed in CoolPlot 1.0; use add_cycle ...`**
: The names deprecated from 0.5 to 0.9 are gone in 1.0; the message
  names the replacement. See {doc}`../upgrade`.

**A line is missing without a warning**
: A line whose value sits at the very edge of the region touches the
  chart at one point only (the first and last value of an evenly spaced
  family can do that); it is left out silently.

**A chart of a blend takes minutes**
: CoolProp 8 is required; with it a default p-h chart of R410A takes
  about five seconds. In an application use `background="processes"`.

**CoolProp's own messages**
: They are passed on in the error; the fluid string and the inputs are
  usually enough to reproduce them with CoolProp directly.
