# How the lines are computed

Every line is a sequence of states computed by CoolProp. What CoolPlot
decides is which states, how many, and how the two-phase region is
handled. The details and the measurements are in the design document,
{doc}`../contributing/architecture` (section 11); this page is the
short version.

## Stepping

A line of constant property is followed in temperature or pressure,
whichever CoolProp solves best together with the constant (an isotherm
in pressure, an isentrope in pressure, an isochore in temperature). The
step is chosen from the shape of the line on the page: a step is
accepted when the drawn segment is short (`2.5 / points` of the chart)
and the line does not turn by more than 5 degrees between two points.
Straight parts get few points, bends more, and the resolution is the
same in every unit system because it is measured in fractions of the
axes. Nothing is computed outside the area the axes show, except the
few points that locate where a line leaves or enters it.

## The two-phase region

An isotherm or isobar meets the dome at one temperature or pressure.
Its single-phase parts stop exactly at the bubble and dew states, and
the part in between is stepped in vapour quality: a straight tie line
for a pure fluid, the temperature glide for a blend. Every other line
crosses the dome where the phase of its points changes; the saturation
state there is found on the saturation curve (pure fluids) or on
CoolProp's phase envelope (mixtures) and inserted, so the kink sits on
the dome.

## Pure fluids and blends

A pure fluid is flashed: CoolProp's flashes of pure fluids are fast and
reliable, and every point round-trips through CoolProp's inverse flash
to about 1e-8. A mixture is traced: each single-phase point is a Newton
iteration in temperature and density started from the previous point,
each two-phase point a one-dimensional solve for the vapour quality
between the saturation states, warm started from the previous quality.
That is what makes a blend chart take seconds rather than minutes. Near
the critical point, where CoolProp's saturation solver stops answering,
a root is judged by the densities of the phase envelope; what cannot be
judged is handed to a cold CoolProp flash, which is slow but safe.

Points CoolProp cannot compute leave a gap in the line, drawn as a gap,
never interpolated across.

## Quality lines

For a pure fluid the lines of constant quality are saturation states on
a temperature grid that is denser towards the critical point, which is
appended. For a mixture, the bubble and dew lines are the two branches
of CoolProp's phase envelope, which follows the dome through the
critical region where the saturation solver fails; a line of
intermediate quality is stepped up to the top of the envelope.

## The C++ port in CoolProp

CoolProp carries a C++ port of the three modules above as
`CoolProp::Plot` (`src/CoolPropPlot.cpp` in the CoolProp repository),
exposed to Python as `CoolProp.CoolProp.Plot`. When the installed
CoolProp has it, {func}`coolplot.thermo.provider.compute_curve` sends
every fluid line there, see {mod}`coolplot.thermo.native`: the same
stepping, tracer and crossings, point for point, with the GIL released
while the line is computed, so background calculation keeps a window
responsive. The time of a chart is mostly CoolProp's own solvers, so the
port saves the Python overhead only: half the time of a pure-fluid chart,
a tenth of a blend's. The Python modules stay the reference the tests
check, and do the work when the port is absent, when the native mode is
"off" (`coolplot.set_native_mode("off")` or the environment variable
`COOLPLOT_NATIVE=0`), or for a model the port cannot take
(binary interaction parameters set on the state, mass fractions on a
Helmholtz backend). Humid-air lines and the states of cycles are not
part of the port.
