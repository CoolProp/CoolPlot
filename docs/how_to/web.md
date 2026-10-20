# In the browser, and in the background

## A chart in a web page

`coolplot.render.web.WebRenderer` writes the same SVG as the SVG writer
but sends only what changed to a small JavaScript client, and turns the
browser's pointer input into the same events as matplotlib (dragging
empty space pans, the wheel zooms):

```python
from coolplot.render.web import WebRenderer
from coolplot.interaction import Interaction

renderer = WebRenderer(width=1000, height=700)
Interaction(diagram, renderer)
renderer.sync(diagram.update_scene(renderer.plot_size_pt()))
```

In your web application, send the messages from
`renderer.listen(callback)` to the browser (over a websocket, say), feed
the client's input to `renderer.receive(message)`, and serve
`renderer.page(stream=..., input=...)`. `receive` checks every message
and raises `ValueError` for a malformed one; answer that with an error
instead of passing it on. `save("chart.html")` writes a static page.

`examples/web_app/` does all this with a small development server
(`server.py`, standard library only):

```
python examples/web_app/app.py
```

That server is meant for development and small tools on your own
machine. It binds to 127.0.0.1, only answers requests that name it in
their `Host` header and only takes input from its own page, so other web
sites open in the browser cannot drive it. Bound to another address it
serves anyone who can reach it, without authentication; put a real web
server in front of it for that.

## Calculating in the background

```python
diagram = PropertyDiagram("HEOS::R32[0.7]&R125[0.3]", "ph", background="processes",
                          on_ready=lambda d: app.call_soon(redraw))   # your GUI's way to run on its thread
renderer.sync(diagram.update_scene())   # returns at once: previews first, then the final lines
diagram.progress                         # (ready, needed)
```

With `background="threads"` or `"processes"`, `update_scene()` never
waits for a line. Missing lines are queued, first coarse
(`Settings.calc.preview_points`) and then at full resolution, and
`on_ready(diagram)` is called from a worker when more is ready; call
`update_scene()` again then. Work the latest picture no longer needs is
cancelled. Threads keep pure-fluid charts responsive; for blends use
processes, which compute in parallel and never block the application.
`diagram.wait()` blocks until all work is done, `diagram.close()` stops
the workers, and `draw()`, `show()` and `save()` wait for the complete
picture. A line whose calculation fails is tried once more and then
skipped with a warning naming the error. On Linux, worker processes are
started by forking the application; start the diagram before your GUI
starts other threads.
