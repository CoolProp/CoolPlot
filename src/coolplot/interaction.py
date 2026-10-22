# -*- coding: utf-8 -*-
"""Turning backend events into diagram changes.

:class:`Interaction` connects a :class:`coolplot.PropertyDiagram` with a
renderer that produces events (capability "events") and handles the
usual cases, so that an interactive application needs only a few lines:

* zooming and panning in the backend set the diagram's view, which
  lays out the labels for the new window (no property calculations);
* a resized plot area lays out the labels again;
* hovering reports the full state under the pointer to ``on_hover``;
* dragging a state marker of a cycle moves that state (see
  :meth:`coolplot.Chart.move_cycle_state`); only the cycle is
  recalculated and redrawn. Air processes on a psychrometric chart are
  cycles too, so their states can be dragged the same way.

Everything goes through the public API of the diagram and the renderer;
an application that wants different behaviour can handle the events
itself with ``renderer.connect(callback)``.
"""
from __future__ import annotations

from typing import Callable, Optional

from .core.events import Click, Drag, DragEnd, DragStart, Hover, Resized, ViewChanged


class Interaction:
    """Handle the events of ``renderer`` for ``diagram``

    Parameters
    ----------
    diagram : Chart
        A PropertyDiagram or a PsychrometricChart.
    renderer : Renderer
        A backend with the "events" capability.
    on_hover : callable, optional
        ``on_hover(state, event)``: the StatePoint under the pointer (None
        where CoolProp has no state) and the Hover event.
    on_click : callable, optional
        ``on_click(event)`` for clicks.
    drag_states : bool
        Let the user drag the states of cycles.
    follow_view : bool
        Take over zoom and pan from the backend.
    """

    def __init__(self, diagram, renderer, on_hover: Optional[Callable] = None, on_click: Optional[Callable] = None,
                 drag_states: bool = True, follow_view: bool = True):
        if "events" not in getattr(renderer, "capabilities", ()):
            raise ValueError("{0} does not produce events.".format(type(renderer).__name__))
        self.diagram = diagram
        self.renderer = renderer
        self.on_hover = on_hover
        self.on_click = on_click
        self.drag_states = drag_states
        self.follow_view = follow_view
        self._token = renderer.connect(self.handle)

    def close(self):
        """Stop handling events of the renderer."""
        self.renderer.disconnect(self._token)

    def redraw(self):
        """Bring the renderer up to date, with labels laid out for its plot size."""
        return self.renderer.sync(self.diagram.update_scene(self.renderer.plot_size_pt()))

    # Event handling ----------------------------------------------------------
    def handle(self, event):
        """Handle one event from the renderer, see :mod:`coolplot.core.events`."""
        if isinstance(event, ViewChanged) and self.follow_view:
            self.diagram.set_view(event.x_limits, event.y_limits)
            self.redraw()
        elif isinstance(event, Resized):
            self.redraw()
        elif isinstance(event, Hover) and self.on_hover is not None:
            self.on_hover(self._state_at(event.x, event.y), event)
        elif isinstance(event, Click) and self.on_click is not None:
            self.on_click(event)
        elif isinstance(event, (DragStart, Drag, DragEnd)) and self.drag_states:
            self._drag(event)

    def _state_at(self, x: float, y: float):
        try:
            return self.diagram.state_at(x, y)
        except (ValueError, KeyError):
            return None   # outside the range of the equation of state (a PropertyError is a ValueError)

    def _drag(self, event):
        target = self.cycle_state(event.item_id, event.index)
        if target is None:
            return
        name, number = target
        try:
            self.diagram.move_cycle_state(name, number, event.x, event.y)
        except (ValueError, KeyError):
            return   # no valid state there: keep the last good position
        self.redraw()

    def cycle_state(self, item_id: Optional[str], index: Optional[int]):
        """(name, state number) of point ``index`` of the marker item of a
        cycle ("cycle/<name>/states"), or None."""
        if item_id is None or index is None or not item_id.endswith("/states"):
            return None
        if not item_id.startswith("cycle/"):
            return None
        name = item_id[len("cycle/"):-len("/states")]
        cycle = next((c for c in self.diagram.spec.cycles if c.name == name), None)
        if cycle is None or not 0 <= index < len(cycle.states):
            return None
        # The marker item lists the states in ascending number, like CycleSpec.states
        return name, cycle.states[index][0]
