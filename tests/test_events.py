# -*- coding: utf-8 -*-
"""Events from the backends and the Interaction helper."""
import pytest

pytest.importorskip("matplotlib")
pytest.importorskip("CoolProp")

from coolplot import PropertyDiagram  # noqa: E402
from coolplot.core.events import ViewChanged  # noqa: E402
from coolplot.interaction import Interaction  # noqa: E402
from coolplot.render.mpl import MatplotlibRenderer  # noqa: E402
from coolplot.render.svg import SvgRenderer  # noqa: E402
from coolplot.render.testing import check_events  # noqa: E402


def _mpl():
    return MatplotlibRenderer(use_pyplot=False)


HEAT_PUMP = [{"p": 3.0, "T": 0.0}, {"p": 15.0, "via": "compression", "eta_is": 0.7},
             {"p": 15.0, "Q": 0.0}, {"p": 3.0, "via": "isenthalpic"}]


@pytest.fixture
def app():
    diagram = PropertyDiagram("HEOS::R290", "ph", tp_limits="ACHP")
    diagram.set_isolines("Q", num=3)
    diagram.set_isolines("T", values=[-20.0, 0.0, 20.0, 40.0], labels=True)
    diagram.add_cycle("Heat pump", HEAT_PUMP)
    renderer = _mpl()
    hovered = []
    interaction = Interaction(diagram, renderer, on_hover=lambda state, event: hovered.append((state, event)))
    interaction.redraw()
    return diagram, renderer, interaction, hovered


def test_zoom_in_the_backend_sets_the_view(app):
    diagram, renderer, _, _ = app
    misses = diagram.cache.misses
    renderer.simulate_view((300.0, 600.0), (2.0, 20.0))
    assert diagram.scene.axes.x_limits == pytest.approx((300.0, 600.0))
    assert diagram.scene.axes.y_limits == pytest.approx((2.0, 20.0))
    assert diagram.cache.misses == misses   # zooming computes nothing


def test_hover_reports_the_state(app):
    diagram, renderer, _, hovered = app
    renderer.simulate_pointer("move", 500.0, 5.0)
    state, event = hovered[-1]
    assert state.p == pytest.approx(5e5, rel=1e-2) and state.h == pytest.approx(5e5, rel=1e-2)


def test_dragging_a_state_moves_it(app):
    diagram, renderer, _, _ = app
    before = diagram.cycle_states("Heat pump")
    misses = diagram.cache.misses
    # Drag state 3 (condenser outlet) from its place to a higher pressure
    s3 = before[3]
    renderer.simulate_pointer("press", s3.h / 1e3, s3.p / 1e5)
    renderer.simulate_pointer("move", s3.h / 1e3 + 5.0, 18.0)
    renderer.simulate_pointer("release", s3.h / 1e3 + 5.0, 18.0)
    after = diagram.cycle_states("Heat pump")
    assert after[3].p == pytest.approx(18e5, rel=2e-2)
    assert after[4].h == pytest.approx(after[3].h)        # the valve follows (via isenthalpic)
    assert after[1] == before[1]
    assert diagram.cache.misses == misses                  # no isoline recalculated


def test_dragging_to_an_impossible_place_keeps_the_last_state(app):
    diagram, renderer, interaction, _ = app
    before = diagram.cycle_states("Heat pump")
    with pytest.raises(ValueError):
        diagram.move_cycle_state("Heat pump", 3, -5000.0, 1e6)
    assert diagram.cycle_states("Heat pump") == before
    interaction.handle(type("E", (), {})())   # unknown events are ignored


def test_interaction_needs_events():
    diagram = PropertyDiagram("R290", "ph")
    with pytest.raises(ValueError):
        Interaction(diagram, SvgRenderer())


def test_matplotlib_passes_the_events_check():
    assert check_events(_mpl) == []


def test_events_check_rejects_broken_backends():
    class SyncReportsView(MatplotlibRenderer):
        def _sync(self, scene):
            report = super()._sync(scene)
            self._emit(ViewChanged(tuple(self.ax.get_xlim()), tuple(self.ax.get_ylim())))
            return report

    class PixelCoordinates(MatplotlibRenderer):
        def _data(self, mouse_event):
            return float(mouse_event.x), float(mouse_event.y)

    class NoHitTest(MatplotlibRenderer):
        def _hit(self, mouse_event):
            return None, None

    for cls in (SyncReportsView, PixelCoordinates, NoHitTest):
        assert check_events(lambda cls=cls: cls(use_pyplot=False)) != [], cls.__name__
