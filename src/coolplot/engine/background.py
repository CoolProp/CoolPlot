# -*- coding: utf-8 -*-
"""Computing curves in the background, so that applications stay responsive.

:class:`BackgroundEngine` is an :class:`coolplot.engine.Engine` that never
waits for a curve. Asked for the curves of a plan, it returns those that
are ready and queues the others on a pool of worker threads or processes:

* Coarse then fine: a missing curve is first computed with
  ``Settings.calc.preview_points`` points and then with full resolution.
  The preview is drawn in the meantime; the final curve replaces it under
  the same item id, so a renderer updates the line in place.
* Every request for curves starts a new generation. Queued work that the
  latest plan no longer needs is cancelled. Work already running is left
  to finish, and its result is cached for later.
* When work finishes, ``on_ready`` is called, never from the thread that
  asks for curves and never with the engine locked. A GUI application
  passes this on to its own event loop and then asks the diagram for a
  new scene. There is at most one notification between two requests for
  curves, so a slow application is not flooded.
* A computation that fails is tried once more on the next request; if it
  fails again the line is skipped with a warning naming the error. When
  a worker process dies (a crash inside CoolProp), every job of that pool
  fails and nobody knows which one crashed: the pool is replaced, and the
  jobs it lost are tried again each in a process of its own, so that only
  the line that really crashes is given up.

One engine serves one diagram: every request for curves replaces the
previous plan. Diagrams share curves by sharing a cache instead.

Workers only receive plain data (the fluid model, the request, the region
and the calculation settings) and return a :class:`Curve`, which is what
makes process workers possible. Each worker builds its own CoolProp state,
because states are not thread safe.

Domains (the calculation region) and cycles are still computed right away:
they are needed before anything can be drawn and are fast.
"""
from __future__ import annotations

import threading
import weakref
from concurrent.futures import BrokenExecutor, Future, ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import replace
from typing import Callable, Dict, Optional, Tuple

from ..spec.diagram import DiagramSpec
from ..thermo.isolines import Curve
from ..thermo.provider import compute_curve as _compute_curve, make_provider
from .cache import CurveCache
from .engine import Engine
from .plan import CurveRequest, Domain

MODES = ("threads", "processes")

# Fluids of the current worker, one set per thread (and so per process).
_local = threading.local()


def _worker_fluid(fluid_spec):
    """The property provider of this worker for a FluidSpec or HumidAirSpec."""
    fluids = getattr(_local, "fluids", None)
    if fluids is None:
        fluids = _local.fluids = {}
    if fluid_spec not in fluids:
        if len(fluids) > 8:
            fluids.clear()
        fluids[fluid_spec] = make_provider(fluid_spec)
    return fluids[fluid_spec]


def compute_curve(fluid_spec, diagram, key: str, value_SI: float, points: int,
                  tp_box: Tuple[float, float, float, float], solver: str, margin: float, spacing: str,
                  ranges=None) -> Curve:
    """One curve from plain data; runs in a worker thread or process."""
    return _compute_curve(_worker_fluid(fluid_spec), diagram, key, value_SI, tp_box, points, solver, margin,
                          spacing, ranges)


class BackgroundEngine(Engine):
    """An Engine that computes curves on worker threads or processes

    Parameters
    ----------
    mode : str
        "threads" (default): one worker thread in the same process. CoolProp
        holds the Python interpreter lock during each call, so threads
        cannot compute in parallel, and long calls (blends) make the
        application stutter; for pure fluids the calls are short and the
        application stays responsive.
        "processes": workers run in parallel on several cores and never
        block the application; starting them takes a moment. Use this for
        blends.
    workers : int, optional
        Number of workers; default 1 for threads and the number of cores
        for processes.
    on_ready : callable, optional
        Called as ``on_ready(engine)`` from another thread when work has
        finished.
    cache : CurveCache, optional
        Store for the curves.
    """

    #: Attempts per curve before it is skipped with a warning.
    MAX_TRIES = 2

    def __init__(self, mode: str = "threads", workers: int = None, on_ready: Callable = None,
                 cache: CurveCache = None):
        super().__init__(cache)
        if mode not in MODES:
            raise ValueError("Unknown background mode '{0}', expected one of {1}.".format(mode, MODES))
        self.mode = mode
        self.on_ready = on_ready
        if workers is None and mode == "threads":
            workers = 1   # more threads only compete for the interpreter lock
        self._workers = workers
        self._pool = self._new_pool()
        self._broken = False
        self._closed = False
        self._failed: Dict[Tuple, Tuple[int, str]] = {}   # key -> (attempts, last error)
        self._suspects = set()    # keys lost with a crashed pool, retried alone
        self._planning = False    # True while curves() works out a new plan
        self.finished_jobs = 0    # jobs that ran to the end, successful or not
        self._submitting = None   # the thread that is queueing work right now
        self.claimed = False      # set by the diagram this engine serves
        # Re-entrant: a job that is already done when it is submitted runs
        # its callback right away, in the submitting thread.
        self._lock = threading.RLock()
        self._needed = set()
        self._needed_final = set()
        self._to_submit = []
        self._jobs: Dict[Tuple, Future] = {}
        self._generation = 0
        self._notified = False
        self._progress = (0, 0)
        self._idle = threading.Event()
        self._idle.set()

    def _new_pool(self, workers=None):
        pool = ThreadPoolExecutor if self.mode == "threads" else ProcessPoolExecutor
        return pool(max_workers=workers or self._workers)

    def _done(self, key) -> bool:
        """True when a final curve needs no more work: computed, or given up."""
        return self.cache.peek(key) is not None or self._failed.get(key, (0,))[0] >= self.MAX_TRIES

    # Asking for curves ----------------------------------------------------
    def curves(self, spec: DiagramSpec, domain: Domain, requests):
        """The curves that are ready; the rest is queued once the scene is built.

        Three steps: start a new plan (``_begin_plan``), collect what the
        cache has through the base class (which calls ``_obtain`` per
        request and notes what is missing), then queue the missing work
        (``_queue_plan``). Worker threads hold the GIL while CoolProp
        computes, so queueing only now keeps this scene quick to build.
        """
        requests = list(requests)
        self._begin_plan()
        try:
            result = super().curves(spec, domain, requests)
        except BaseException:
            with self._lock:
                self._planning = False
                if not self._jobs:
                    self._idle.set()   # wait() must not hang on a failed request
            raise
        self._queue_plan(len(requests))
        return result

    def _begin_plan(self):
        with self._lock:
            if self._closed:
                raise RuntimeError("This BackgroundEngine was closed.")
            if self._broken:
                # A worker process died: its pool takes no more work
                self._pool.shutdown(wait=False, cancel_futures=True)
                self._pool, self._broken = self._new_pool(), False
            self._generation += 1
            self._notified = False
            self._needed = set()
            self._needed_final = set()
            self._to_submit = []
            self._planning = True
            self._idle.clear()   # until the new plan has been queued

    def _queue_plan(self, n_requests: int):
        with self._lock:
            self._submitting = threading.get_ident()
            try:
                for args in self._to_submit:
                    self._submit(*args)
            finally:
                self._submitting = None
            self._to_submit = []
            # Cancel queued work the latest plan does not need
            for key, future in list(self._jobs.items()):
                if key not in self._needed and future.cancel():
                    self._jobs.pop(key, None)
            ready = sum(1 for k in self._needed_final if self._done(k))
            self._progress = (ready + n_requests - len(self._needed_final), n_requests)
            self._planning = False
            if not self._jobs:
                self._idle.set()

    def _obtain(self, spec: DiagramSpec, domain: Domain, request: CurveRequest):
        """(curve, final): the final curve if ready, else the preview, else None."""
        key = self.cache_key(spec, domain, request)
        preview_points = spec.settings.calc.preview_points
        preview = None
        if 0 < preview_points < request.points:
            preview = replace(request, points=preview_points)
        with self._lock:
            curve = self.cache.peek(key)
            if curve is not None:
                self.cache.hits += 1
                return curve, True
            attempts, error = self._failed.get(key, (0, ""))
            if attempts >= self.MAX_TRIES:
                self._needed_final.add(key)
                self._warn(spec, domain, request, "Skipping the line {0}={1:.6g} in {2}: the calculation failed "
                           "with {3}".format(request.key, request.value_SI, spec.fluid.name, error))
                return None, False
            self._needed.add(key)
            self._needed_final.add(key)
            preview_curve = None
            if preview is not None:
                preview_key = self.cache_key(spec, domain, preview)
                self._needed.add(preview_key)
                preview_curve = self.cache.peek(preview_key)
                if preview_curve is None:
                    self._to_submit.append((spec, domain, preview, preview_key))
            self._to_submit.append((spec, domain, request, key))
        return preview_curve, False

    def _submit(self, spec: DiagramSpec, domain: Domain, request: CurveRequest, key: Tuple):
        """Queue one curve unless it is already queued or running (lock held)."""
        if key in self._jobs:
            return
        calc = spec.settings.calc
        self.cache.misses += 1
        # A job lost with a crashed pool runs alone, so a crash names its culprit
        alone = key in self._suspects
        pool = self._new_pool(workers=1) if alone else self._pool
        future = pool.submit(compute_curve, spec.fluid, spec.diagram, request.key, request.value_SI,
                             request.points, domain.tp_box, calc.solver, calc.critical_margin,
                             calc.saturation_spacing, domain.ranges_SI)
        if alone:
            pool.shutdown(wait=False)   # the process ends after this one job
        self._jobs[key] = future
        self._idle.clear()
        # The callback keeps only a weak reference to the pool. With a strong
        # one, the pool of a crashed worker would be freed by its own manager
        # thread while that thread holds the pool's lock, and the pool's clean
        # up takes the same lock: the thread hangs and Python cannot exit
        # (seen with Python 3.12.3; newer versions take no lock there).
        pool_ref = weakref.ref(pool)
        future.add_done_callback(lambda f, key=key, pool_ref=pool_ref, alone=alone:
                                 self._finished(key, f, pool_ref, alone))

    def _finished(self, key: Tuple, future: Future, pool_ref=None, alone: bool = False):
        """Store a result and tell the application (runs in a worker callback).

        ``pool_ref`` is a weak reference to the pool that ran the job.
        """
        with self._lock:
            if self._jobs.get(key) is future:
                del self._jobs[key]
            notify = False
            if not future.cancelled():
                self.finished_jobs += 1
                self._record(key, future, pool_ref, alone)
                notify = self._count_progress(key)
            if not self._jobs and not self._planning:
                self._idle.set()
            if self._closed:
                notify = False   # nobody may ask for curves any more
            # A job that was already done when it was queued lands here in the
            # thread that asks for curves, with the engine locked: tell the
            # application from another thread, as for any other job.
            here = self._submitting == threading.get_ident()
        if notify and self.on_ready is not None:
            if here:
                threading.Thread(target=self.on_ready, args=(self,), daemon=True).start()
            else:
                self.on_ready(self)

    def _count_progress(self, key: Tuple) -> bool:
        """Count a finished job for the latest plan; True if the application is due a notification."""
        if key in self._needed_final and self._done(key):
            ready, total = self._progress
            self._progress = (min(ready + 1, total), total)
        if key in self._needed and not self._notified:
            self._notified = True
            return True
        return False

    def _record(self, key: Tuple, future: Future, pool_ref, alone: bool):
        """Keep the outcome of one job: the curve, a crashed pool, or a failure (lock held).

        ``pool_ref`` is a weak reference to the pool that ran the job.
        """
        error = future.exception()
        if error is None:
            self.cache.put(key, future.result())
            self._failed.pop(key, None)
            self._suspects.discard(key)
        elif isinstance(error, BrokenExecutor) and not alone:
            # Some job crashed the shared pool, maybe not this one: no
            # attempt is counted, the job is retried alone
            self._suspects.add(key)
            if pool_ref is not None and pool_ref() is self._pool:
                self._broken = True   # replaced on the next request
        else:
            # Not cached: the next request tries again, up to MAX_TRIES
            attempts = self._failed.get(key, (0, ""))[0] + 1
            if len(self._failed) > 10000:   # a long session with many failing lines, not a leak
                self._failed.clear()
                self._suspects.clear()
            self._failed[key] = (attempts, "{0}: {1}".format(type(error).__name__, error))

    # State ----------------------------------------------------------------
    @property
    def progress(self) -> Tuple[int, int]:
        """(final curves ready, curves needed) for the latest plan."""
        return self._progress

    @property
    def busy(self) -> bool:
        with self._lock:
            return bool(self._jobs)

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Block until no work is queued or running; False on timeout."""
        return self._idle.wait(timeout)

    def close(self):
        """Stop the workers; queued work is cancelled, the engine takes no more requests."""
        with self._lock:
            self._closed = True
            self._pool.shutdown(wait=False, cancel_futures=True)
            # Cancelled jobs have left _jobs through _finished; running ones finish
            if not self._jobs:
                self._idle.set()
