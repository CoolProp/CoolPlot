# -*- coding: utf-8 -*-
"""Traced lines kept on disk between runs (coolplot.engine.store), the way CoolProp keeps its tables."""
import glob
import json
import os
import subprocess
import sys
import zlib

import numpy as np
import pytest

pytest.importorskip("CoolProp")

from coolplot import PropertyDiagram  # noqa: E402
from coolplot.engine import CurveCache  # noqa: E402
from coolplot.engine import store as store_module  # noqa: E402
from coolplot.engine.store import REVISION, SUFFIX, CurveStore, fluid_folder, key_text  # noqa: E402
from coolplot.spec import FluidSpec, HumidAirSpec  # noqa: E402

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _chart(cache):
    chart = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP", settings="interactive",
                            cache=cache)
    chart.set_lines("T", num=5, labels=True)
    chart.set_lines("s", at_saturation={"T": 20, "range": (-20, 40)}, labels=True)
    chart.set_lines("Q", num=3)
    return chart


def _files(directory):
    return sorted(glob.glob(os.path.join(str(directory), "*", "*" + SUFFIX)))


def test_a_second_cache_reads_every_line_from_disk(tmp_path):
    first = CurveCache(directory=str(tmp_path))
    scene = _chart(first).update_scene()
    assert first.misses > 0 and first.disk.saved == first.misses and first.disk_hits == 0
    assert [os.path.basename(os.path.dirname(f)) for f in _files(tmp_path)] == ["HEOS(R290)"] * first.misses

    second = CurveCache(directory=str(tmp_path))
    again = _chart(second).update_scene()
    assert second.misses == 0 and second.disk_hits == first.misses and second.disk.saved == 0
    for item in scene:
        if item.id.startswith("iso/") and not item.id.endswith("/label"):
            assert np.array_equal(np.asarray(item.x), np.asarray(again[item.id].x), equal_nan=True), item.id
            assert np.array_equal(np.asarray(item.y), np.asarray(again[item.id].y), equal_nan=True), item.id
    # Other inputs, other lines: the key is not too coarse
    third = CurveCache(directory=str(tmp_path))
    other = _chart(third)
    other.settings = other.settings.with_(calc={"points": 61})
    other.update_scene()
    from coolplot.engine import plan
    n_quality = len([r for r in plan(other.spec, other.engine.domain(other.spec)) if r.key == "Q"])
    # Lines of constant quality are traced in saturation points, not in Settings.calc.points: they are reused
    assert n_quality > 0 and third.disk_hits == n_quality and third.misses == first.misses - n_quality


def test_another_process_with_another_hash_seed_finds_the_lines(tmp_path):
    """The key, CoolProp's configuration included, is the same text in every process."""
    script = ("import sys, warnings; warnings.simplefilter('ignore');"
              "sys.path.insert(0, {0!r});"
              "from coolplot.engine import CurveCache;"
              "import test_curve_store as t;"
              "c = CurveCache(directory=sys.argv[1]); t._chart(c).update_scene();"
              "print(c.misses, c.disk_hits)").format(os.path.join(ROOT, "tests"))
    counts = []
    for seed in ("1", "2"):
        env = dict(os.environ, PYTHONHASHSEED=seed, MPLBACKEND="Agg")
        out = subprocess.run([sys.executable, "-c", script, str(tmp_path)], capture_output=True, text=True, env=env,
                             timeout=600)
        assert out.returncode == 0, out.stderr
        counts.append(tuple(int(v) for v in out.stdout.split()))
    (computed, _), (computed_again, read) = counts
    assert computed > 0 and computed_again == 0 and read == computed


def test_a_damaged_file_is_traced_again_and_replaced(tmp_path):
    cache = CurveCache(directory=str(tmp_path))
    _chart(cache).update_scene()
    files = _files(tmp_path)
    with open(files[0], "wb") as f:
        f.write(b"not a compressed record")
    second = CurveCache(directory=str(tmp_path))
    _chart(second).update_scene()
    assert second.misses == 1 and second.disk.rejected == 1 and second.disk.saved == 1
    record = json.loads(zlib.decompress(open(files[0], "rb").read()))
    assert record["revision"] == REVISION


@pytest.mark.parametrize("change", ["revision", "key"])
def test_a_file_of_another_revision_or_key_is_not_used(tmp_path, change):
    cache = CurveCache(directory=str(tmp_path))
    _chart(cache).update_scene()
    path = _files(tmp_path)[0]
    record = json.loads(zlib.decompress(open(path, "rb").read()))
    record[change] = REVISION + 1 if change == "revision" else record["key"] + " "   # a digest collision
    with open(path, "wb") as f:
        f.write(zlib.compress(json.dumps(record).encode("utf-8")))
    second = CurveCache(directory=str(tmp_path))
    _chart(second).update_scene()
    assert second.misses == 1 and second.disk.rejected == 1


def test_the_size_limit_of_coolprops_tables_applies(tmp_path, monkeypatch):
    import CoolProp.CoolProp as CP
    key = CP.MAXIMUM_TABLE_DIRECTORY_SIZE_IN_GB
    old = CP.get_config_double(key)
    CP.set_config_double(key, 2.5)
    try:
        assert CurveStore(str(tmp_path)).limit_GB == 2.5   # read from CoolProp, not assumed
    finally:
        CP.set_config_double(key, old)

    store = CurveStore(str(tmp_path))
    store.limit_GB = 1e-12   # every line is above the limit
    store._size_bytes = 0
    with pytest.warns(UserWarning, match="1.5 times"):
        assert not store._room_for(1000)
    store.limit_GB = 1000.0 / 1024.0 ** 3     # between the limit and 1.5 times it: kept, with a warning
    store._size_bytes = 300
    with pytest.warns(UserWarning, match="more than CoolProp"):
        assert store._room_for(1000)
    cache = CurveCache(directory=str(tmp_path))
    cache.disk.limit_GB = 1e-12
    with pytest.warns(UserWarning, match="1.5 times"):
        _chart(cache).update_scene()
    assert cache.disk.saved == 0 and _files(tmp_path) == [] and cache.disk._writable


def test_where_the_folder_is(tmp_path, monkeypatch):
    import CoolProp.CoolProp as CP
    monkeypatch.delenv("COOLPLOT_CACHE_DIR", raising=False)
    assert CurveCache().disk is None                      # a one-shot script writes nothing
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert CurveCache(directory=True).disk.directory == os.path.join(str(tmp_path), ".CoolProp", "CoolPlot",
                                                                     "Curves")
    key = CP.ALTERNATIVE_TABLES_DIRECTORY
    old = CP.get_config_string(key)
    CP.set_config_string(key, str(tmp_path / "tables"))
    try:   # CoolPlot's folder moves with CoolProp's tables
        assert CurveCache(directory=True).disk.directory == os.path.join(str(tmp_path / "tables"), "CoolPlot",
                                                                         "Curves")
    finally:
        CP.set_config_string(key, old)
    monkeypatch.setenv("COOLPLOT_CACHE_DIR", str(tmp_path / "chosen"))
    assert CurveCache().disk.directory == str(tmp_path / "chosen")
    assert CurveCache(directory=True).disk.directory == str(tmp_path / "chosen")
    assert CurveCache(directory=False).disk is None
    assert CurveCache(directory=str(tmp_path / "given")).disk.directory == str(tmp_path / "given")


def test_a_folder_that_cannot_be_written_only_warns(tmp_path):
    blocker = tmp_path / "a file"
    blocker.write_text("in the way")
    cache = CurveCache(directory=str(blocker))
    with pytest.warns(UserWarning, match="cannot be kept"):
        scene = _chart(cache).update_scene()
    assert len(scene) > 10 and cache.disk.saved == 0


def test_folder_names_and_keys():
    assert fluid_folder(FluidSpec.parse("HEOS::R290")) == "HEOS(R290)"
    assert fluid_folder(FluidSpec.parse("HEOS::R32[0.7]&R125[0.3]")) == "HEOS(R32[0.7000000000]&R125[0.3000000000])"
    assert fluid_folder(HumidAirSpec(101325.0)) == "HumidAir(p=101325.0)"
    a = (FluidSpec.parse("HEOS::R290"), ("8.0.0", "abc"), 1.0 / 3.0, float("nan"))
    assert key_text(a) == key_text((FluidSpec.parse("HEOS::R290"), ("8.0.0", "abc"), 1.0 / 3.0, float("nan")))
    assert key_text(a) != key_text((a[0], ("8.0.0", "abd")) + a[2:])          # another CoolProp configuration
    assert key_text(a) != key_text(a[:2] + (np.nextafter(1.0 / 3.0, 1.0),) + a[3:])   # one bit apart
    with pytest.raises(TypeError):
        key_text((object(),))
    store = CurveStore("unused")
    assert store.path((object(),)) == (None, None)


def test_the_fingerprint_is_the_same_text_in_every_process():
    from coolplot.thermo import Fluid
    fingerprint = Fluid("HEOS::R290").fingerprint
    assert isinstance(fingerprint[1], str) and len(fingerprint[1]) == 16
    code = "from coolplot.thermo import Fluid; print(Fluid('HEOS::R290').fingerprint[1])"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env=dict(os.environ, PYTHONHASHSEED="7"), timeout=300)
    assert out.stdout.strip() == fingerprint[1]


def test_a_background_engine_takes_the_lines_from_disk_at_once(tmp_path):
    _chart(CurveCache(directory=str(tmp_path))).update_scene()
    cache = CurveCache(directory=str(tmp_path))
    chart = PropertyDiagram("HEOS::R290", "ph", units="engineering", tp_limits="ACHP", settings="interactive",
                            cache=cache, background="threads")
    chart.spec = _chart(None).spec
    try:
        scene = chart.update_scene()   # no waiting: every line is on disk
        assert cache.misses == 0 and cache.disk_hits > 0
        assert len([i for i in scene if i.id.startswith("iso/s/") and not i.id.endswith("/label")]) == 4
    finally:
        chart.close()


def test_the_module_does_not_touch_the_disk_unless_asked(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(store_module.CurveStore, "load", lambda self, key: calls.append(key))
    monkeypatch.setattr(store_module.CurveStore, "save", lambda self, key, curve: calls.append(key))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    for value in (None, "0", "off", ""):
        if value is None:
            monkeypatch.delenv("COOLPLOT_CACHE_DIR", raising=False)
        else:
            monkeypatch.setenv("COOLPLOT_CACHE_DIR", value)
        _chart(None).update_scene()
    assert calls == [] and list(tmp_path.iterdir()) == []


def test_every_input_of_a_line_changes_its_file(tmp_path):
    from dataclasses import replace
    from coolplot.engine import Engine, plan
    chart = _chart(None)
    spec = chart.spec
    engine = Engine()
    domain = engine.domain(spec)
    request = [r for r in plan(spec, domain) if r.key == "T"][0]
    store = CurveStore(str(tmp_path))
    base = store.path(engine.cache_key(spec, domain, request))[0]
    variants = [
        engine.cache_key(spec, domain, replace(request, points=request.points + 1)),
        engine.cache_key(spec, domain, replace(request, value_SI=request.value_SI + 1e-6)),
        engine.cache_key(spec.with_(settings=spec.settings.with_(calc={"solver": "flash"})), domain, request),
        engine.cache_key(spec, replace(domain, tp_box=domain.tp_box[:3] + (domain.tp_box[3] * 0.9,)), request),
        engine.cache_key(spec.without_isolines("s").with_(diagram="hs"), domain, request),
    ]
    paths = {store.path(k)[0] for k in variants}
    assert base not in paths and len(paths) == len(variants)
    other_build = CurveStore(str(tmp_path))
    other_build.environment = ("9.9.9", other_build.environment[1])   # another CoolPlot version
    assert other_build.path(engine.cache_key(spec, domain, request))[0] != base


def test_a_changed_reference_state_never_reaches_the_disk(tmp_path):
    import CoolProp.CoolProp as CP
    cache = CurveCache(directory=str(tmp_path))
    chart = _chart(cache)
    chart.update_scene()
    before = set(_files(tmp_path))
    try:
        CP.set_reference_state("R290", "NBP")   # without engine.refresh()
        again = CurveCache(directory=str(tmp_path))
        moved = _chart(again)
        moved.engine = chart.engine
        moved.engine.cache = again
        moved.update_scene()
        assert again.misses > 0 and again.disk_hits == 0   # the old lines are not served
        assert set(_files(tmp_path)) > before              # the new ones go to new files
    finally:
        CP.set_reference_state("R290", "DEF")
        chart.engine.refresh()
