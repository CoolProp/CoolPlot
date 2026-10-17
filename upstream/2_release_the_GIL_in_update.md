Title: Python binding: release the GIL during AbstractState.update and the other flash calls

CoolProp 8.0.0, nanobind binding.

`AbstractState.update` holds the Python interpreter lock for the whole flash. Two Python threads doing R410A p,Q flashes (0.35 ms each) on a four-core machine get a speed-up of 1.3x, two threads doing R290 h,p flashes 1.2x, i.e. no parallelism:

```python
import time, threading, CoolProp, CoolProp.CoolProp as CP
def work(n):
    s = CP.AbstractState("HEOS", "R32&R125"); s.set_mole_fractions([0.697615, 0.302385])
    for i in range(n): s.update(CoolProp.PQ_INPUTS, 1e6 + i, 0.5)
t0 = time.perf_counter(); work(400); work(400); serial = time.perf_counter() - t0
t0 = time.perf_counter(); ts = [threading.Thread(target=work, args=(400,)) for _ in range(2)]
[t.start() for t in ts]; [t.join() for t in ts]; print(serial / (time.perf_counter() - t0))   # 1.32
```

Proposal: wrap `update` (and `update_with_guesses`, the `*_flash` helpers, `PropsSI`, `HAPropsSI`) with `nb::call_guard<nb::gil_scoped_release>()`. Each AbstractState is used from one thread at a time in every case I know of; the global fluid library and configuration are already read-only after start-up. Applications that draw property diagrams of blends (tens of seconds of mixture flashes per chart) could then use a thread pool instead of processes.
