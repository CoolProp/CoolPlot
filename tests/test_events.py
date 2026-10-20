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


def _events(renderer):
    seen = []
    renderer.connect(seen.append)
    return seen


def test_release_outside_the_axes_has_coordinates(app):
    import math
    diagram, renderer, _, _ = app
    seen = _events(renderer)
    s1 = diagram.cycle_states("Heat pump")[1]
    renderer.simulate_pointer("press", s1.h / 1e3, s1.p / 1e5)
    (x0, x1), (y0, y1) = renderer.ax.get_xlim(), renderer.ax.get_ylim()
    renderer.simulate_pointer("move", x0 - 0.05 * (x1 - x0), s1.p / 1e5)   # into the margin
    renderer.simulate_pointer("release", x0 - 0.05 * (x1 - x0), s1.p / 1e5)
    end = seen[-1]
    assert type(end).__name__ == "DragEnd" and math.isfinite(end.x) and math.isfinite(end.y)


def test_click_only_without_moving_and_drag_only_with_the_left_button(app):
    diagram, renderer, _, _ = app
    seen = _events(renderer)
    renderer.simulate_pointer("press", 300.0, 1.5)
    renderer.simulate_pointer("move", 350.0, 1.5)
    renderer.simulate_pointer("release", 350.0, 1.5)
    assert [type(e).__name__ for e in seen] == []   # moved: no Click, no Hover while pressed
    s1 = diagram.cycle_states("Heat pump")[1]
    before = diagram.cycle_states("Heat pump")[1].h
    renderer.simulate_pointer("press", s1.h / 1e3, s1.p / 1e5, button=3)
    renderer.simulate_pointer("move", s1.h / 1e3 + 20.0, s1.p / 1e5)
    renderer.simulate_pointer("release", s1.h / 1e3 + 20.0, s1.p / 1e5, button=3)
    assert diagram.cycle_states("Heat pump")[1].h == before
    assert not any(type(e).__name__.startswith("Drag") for e in seen)


def test_a_lost_release_ends_the_drag(app):
    from matplotlib.backend_bases import MouseEvent
    diagram, renderer, _, _ = app
    seen = _events(renderer)
    s1 = diagram.cycle_states("Heat pump")[1]
    renderer.simulate_pointer("press", s1.h / 1e3, s1.p / 1e5)
    renderer.simulate_pointer("move", s1.h / 1e3 + 10.0, s1.p / 1e5)
    # The button comes up outside the window: the next move holds no button
    x_px, y_px = renderer.ax.transData.transform((s1.h / 1e3 + 30.0, s1.p / 1e5))
    event = MouseEvent("motion_notify_event", renderer.figure.canvas, x_px, y_px, buttons=[])
    renderer.figure.canvas.callbacks.process("motion_notify_event", event)
    names = [type(e).__name__ for e in seen]
    assert "DragEnd" in names and names[-1] == "Hover"


def test_a_zoom_redraws_once(app):
    diagram, renderer, interaction, _ = app
    seen = _events(renderer)
    # The zoom tool sets x and y one after the other, then draws the canvas
    renderer.ax.set_xlim(300.0, 600.0)
    renderer.ax.set_ylim(2.0, 20.0)
    renderer.figure.draw_without_rendering()
    assert [type(e).__name__ for e in seen] == ["ViewChanged"]
    assert renderer.ax.get_xlim() == pytest.approx((300.0, 600.0))
    seen.clear()
    renderer.figure.draw_without_rendering()   # the drawing after the diagram's own sync reports nothing
    assert seen == []


def test_move_cycle_state_needs_a_whole_number(app):
    diagram, _, _, _ = app
    with pytest.raises(ValueError):
        diagram.move_cycle_state("Heat pump", 2.7, 500.0, 10.0)


def test_a_sync_before_the_repaint_keeps_the_zoom(app):
    diagram, renderer, _, _ = app
    seen = _events(renderer)
    renderer.ax.set_xlim(300.0, 600.0)
    renderer.ax.set_ylim(2.0, 20.0)
    renderer.sync(diagram.scene)   # e.g. a background curve arrives, axes unchanged
    renderer.figure.draw_without_rendering()
    assert [type(e).__name__ for e in seen] == ["ViewChanged"]


def test_the_library_events_are_started_on_the_first_connect_only():
    class Counting(SvgRenderer):
        started = 0

        def _start_events(self):
            self.started += 1

    renderer = Counting()
    renderer.connect(lambda event: None)
    renderer.connect(lambda event: None)
    assert renderer.started == 1
