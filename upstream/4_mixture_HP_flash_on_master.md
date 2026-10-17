# CoolProp master: H-p flash of mixtures refuses or misplaces two-phase states that 8.0.0 solves

Observed on master 022b63e (8.1.0dev) against the 8.0.0 wheel, with
CoolPlot's isoline tests (tests/test_numerics.py, tests/test_thermo.py).

1. HEOS::R32[0.7]&R125[0.3], h = 4e5 J/kg, p = 965489 Pa: 8.0.0 returns the
   two-phase state T = 279.239 K, Q = 0.884 (and the same state through a
   scratch state with the phase envelope built). master raises
   "HSU_P_flash for mixture did not converge to the specification:
   residual 1788.25 (target 28969.3) at T=279.211 K ... the (T,p) flash is
   misclassifying the phase for this mixture". The residual gate added
   after 8.0.0 (FlashRoutines.cpp, "Verify the result actually satisfies
   the specification (#3192)") rejects it; the temperature search runs on
   PT flashes, which misclassify the phase inside the dome. 40 pressures
   in 1.5e5..4e5 Pa all solve on 8.0.0.

2. HEOS::R407C.mix, the isochore rho = 100 kg/m3 computed with (Dmass, T)
   inputs on the DEF T-p box: on master the point h = 91161.75 J/kg,
   p = 3572.84 Pa (T about 178 K) flashes back with (Hmass, P) to
   rho = 3.465 kg/m3, T = 178.187 K, Q = 0.0601, which is not the same
   state (a quality 0.06 by mass at 3.6 kPa has about that density; the
   state the (Dmass, T) flash reported must have had Q about 0.002).
   One of the two flashes is wrong. On 8.0.0 the (Dmass, T) flash gives
   29 valid points on this line (master: 45) and every one of them round
   trips through (Hmass, P) to rho = 100 within 1e-3.

Repro: /tmp/.../scratchpad/p07/hp_regression.py (needs CoolPlot).
