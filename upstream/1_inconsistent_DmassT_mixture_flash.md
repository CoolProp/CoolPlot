Title: DmassT flash of a mixture inside the two-phase region returns a single-phase state without raising

CoolProp 8.0.0 (also 7.2.0 and 6.8.0 give the same answer), Linux x86_64, Python 3.13, nanobind binding.

For a mixture, `AbstractState.update(DmassT_INPUTS, rho, T)` with (rho, T) inside the two-phase region sometimes returns a state flagged as gas (Q = -1) whose pressure and enthalpy belong to a different density. No exception is raised, so a caller cannot tell the state is wrong.

Reproduction:

```python
import CoolProp
from CoolProp.CoolProp import AbstractState
st = AbstractState("HEOS", "R407C.mix")
st.update(CoolProp.DmassT_INPUTS, 100.0, 264.16)
print(st.rhomass(), st.Q(), st.phase(), st.p(), st.hmass())
# 100.0 -1.0 iphase_gas 307067 285269
chk = AbstractState("HEOS", "R407C.mix")
chk.update(CoolProp.HmassP_INPUTS, st.hmass(), st.p())
print(chk.rhomass(), chk.T())
# 27.5 258.6   <- the same (h, p) is a gas at 27.5 kg/m3 and 258.6 K, not 100 kg/m3 at 264.16 K
```

At 264.16 K the dew and bubble pressures of R407C are 332 and 419 kPa, with saturated densities of 14.3 (vapour) and 1268 kg/m3 (liquid); 100 kg/m3 lies between them, so the state is two-phase. At 250 K the same call returns a correct two-phase state (Q = 0.101). The same happens for R410A.mix and R32/R1234yf 50/50, with and without a built phase envelope.

Expected: either a two-phase state with 0 <= Q <= 1 and p between the dew and bubble pressure, or a ValueError.

Context: found while verifying isochores drawn by CoolPlot (every point round-tripped through HmassP); CoolPlot now rejects such states by comparing the reported density with the saturated densities at T. Scripts: dt_flash.py from the CoolPlot numerics review.
