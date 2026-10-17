Title: CoolProp::Plot drops the fractions of a blend, and is not exposed to any wrapper

`src/CoolPropPlot.cpp`, `Detail::process_fluid_state`:

```cpp
std::string backend, fluids;
CoolProp::extract_backend(fluid_ref, backend, fluids);
std::vector<double> fractions;
fluids = CoolProp::extract_fractions(fluids, fractions);
return std::shared_ptr<CoolProp::AbstractState>(CoolProp::AbstractState::factory(backend, fluids));
```

`fractions` is parsed and then never set on the state, so `PropertyPlot("HEOS::R32[0.7]&R125[0.3]", ...)` builds a state without mole fractions and every evaluation fails. The fix is `if (!fractions.empty()) state->set_mole_fractions(fractions);` before returning (and `set_mass_fractions` for the INCOMP backend, which reads mass fractions).

Two further observations, as a basis for discussion rather than defects:

1. `CoolProp::Plot` is referenced nowhere else in the repository: not in `src/CoolProp.i`, `nanobind_interface.cxx`, `emscripten_interface.cxx` or `CoolPropLib.h`, so no wrapper can use it (the Python wheel has no plot names in `CoolProp.CoolProp`). If it is meant to be used, including the header in `CoolProp.i` and adding a nanobind module would make it reachable from every scripted-language wrapper.
2. The algorithm is the one from the old `CoolProp.Plots.PropertyPlot`: a fixed grid of x or y values with one flash per point, failures as NaN (and a line on std::cerr), no treatment of the two-phase region or of where a line meets the saturation curve. CoolPlot (github.com/CoolProp/CoolPlot) traces isolines instead and inserts the saturation states; its review for 1.0 proposes porting that tracer into `CoolProp::Plot` so that all wrappers get property diagrams. Happy to open that discussion separately if there is interest.
