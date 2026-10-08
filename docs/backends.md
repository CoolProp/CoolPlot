# Writing a CoolPlot backend

A backend (renderer) draws a `CoolPlot.scene.Scene` with one plotting
library. This guide lists what a backend has to do to be accepted. The
key words MUST, SHOULD and MAY are used as in RFC 2119.

The two backends shipped with CoolPlot are the reference implementations:

* `CoolPlot/render/svg.py`: no dependencies, writes a document. Read this
  one first; it is the simplest complete example.
* `CoolPlot/render/mpl.py`: draws into a live matplotlib Axes and updates
  artists in place.

Acceptance is mechanical: a backend is accepted when the conformance kit
reports no failures.

```python
from CoolPlot.render.testing import run_conformance
assert run_conformance(MyRenderer) == []
```

Every failure message ends with a tag in square brackets, such as
`[style]` or `[order]`, naming the section of this guide it refers to.
A few requirements cannot be checked by reading values back; they are
marked **(manual)** and need a look at the output during review.
`tests/test_backend_conformance.py` plants one defect at a time in the
shipped backends and checks that the kit catches each of them.


## 1. Contract [sync report], [selective update], [clear]

Subclass `CoolPlot.render.base.Renderer`. The base class owns the
bookkeeping: on every `sync(scene)` it compares the scene with what it drew
last time and calls the hooks below only for what changed. A backend MUST
NOT override `sync`.

| Hook | Called when | Must do |
|------|-------------|---------|
| `_set_axes(axes)` | `AxesSpec` changed | apply labels, title, scales, limits and the complete `AxesStyle` |
| `_add(item)` | new item | create the backend object, fully styled, visible or hidden as asked |
| `_update(old, new)` | item changed | make the object match `new`; the default removes and re-adds |
| `_remove(item)` | item gone | delete the backend object |
| `_reorder(order)` | drawing order changed | restack so items draw in `order` (bottom first) |
| `_set_legend(entries, style)` | legend content or style changed | show `(text, items)` entries, or remove the legend when `entries` is empty or `style` is None or not visible |
| `_finish(report)` | end of every sync | request at most one repaint, and do nothing at all unless `report.changed` (manual) |

Requirements:

* A sync of an unchanged scene MUST NOT touch the backend at all.
* Restyling one item MUST NOT touch any other item.
* A backend that can update objects in place SHOULD do so, and then
  declares `"in_place_updates"` in `capabilities`. The kit then checks
  that a restyled item keeps its backend object and that its neighbours
  keep theirs.
* `clear()` MUST remove everything, and a following `sync` MUST draw the
  scene again from scratch.


## 2. Drawing order [order]

Items are drawn bottom to top by `z_order`; items with equal `z_order`
in their order in the scene. `Scene.draw_order()` gives the exact list and
the base class passes it to `_reorder` whenever it changes, including when
a new item belongs between existing ones. An item that changes its type
under the same id keeps its place.

`z_order` is always finite and at least 0 (the scene enforces it). The
grid is drawn below every item; the frame SHOULD be drawn above every
item (manual).


## 3. Styles [style]

The scene carries fully resolved, normalised styles (see
`docs/styling.md`). A backend MUST render every field; it MUST NOT apply
its own defaults, themes or style sheets on top.

**Units.** All lengths are points. A pixel-based backend uses
1 pt = 4/3 px (96 px per inch). Output MAY round lengths, by no more than
0.005 pt.

**Colours** arrive as `#rrggbb` or None (no paint), with alpha separate.
None MUST produce no paint, not black.

**Lines**

* `width_pt`, `color`, `alpha`, `cap`, `join` as given.
* Dashes MUST be drawn with exactly `dash_pattern_pt(style.dash,
  style.width_pt)` from `CoolPlot.style`, final lengths in points. If the
  library scales dashes by line width itself (matplotlib does), compensate
  for it.
* Casing: when `casing_color` is set and `casing_width_pt > 0`, draw the
  same path underneath with width `width_pt + 2 * casing_width_pt`, the
  casing colour, the same dash pattern and alpha, and the same caps
  (manual). The line itself is still drawn on top.

**Markers**

* All seven shapes of `MARKER_SHAPES` MUST be supported: circle `o`,
  square `s`, triangles `^` and `v`, diamond `D`, crosses `x` and `+`.
* `size_pt` is the width of the marker's bounding box, for every shape.
  Libraries do not agree on this (matplotlib draws its diamond 1.41 times
  wider), so check each shape.
* `face_color` None gives a hollow marker. The crosses have no face.
* `edge_width_pt` is the outline width; `alpha` applies to the marker.

**Text**

* Font: try the families of `font.family` in order and fall back to the
  generic family at the end of the list. A backend MAY drop families that
  are not installed, but MUST keep the order and the generic fallback, and
  SHOULD do so silently.
* `size_pt`, `weight`, `style`, `color`, `alpha`, `h_align`, `v_align`.
* Halo: when `halo_color` is set and `halo_width_pt > 0`, draw an outline
  of total width `2 * halo_width_pt` in the halo colour behind the glyphs
  (SVG `paint-order="stroke"`, matplotlib `patheffects.withStroke`), with
  the alpha of the text (manual).
* Direction: `Text.direction = (dx, dy)` is a direction in *data*
  coordinates. The backend MUST rotate the text to follow it on screen,
  taking the axis scales and the aspect ratio into account, and keep it
  upright (between -90 and +90 degrees). Without a direction the text is
  horizontal. If the library supports it, the angle SHOULD stay correct
  after zooming and resizing (matplotlib `transform_rotates_text`).

**Axes**

* Limits arrive ascending (the scene enforces it); inverted axes are not
  supported.
* Axis labels and title with their complete `TextStyle`. Tick labels
  MUST honour font family, size and colour; weight, style, alpha and halo
  MAY be applied.
* `background` behind the plot area, `frame_color` and `frame_width_pt`
  for the frame, tick colour, length, width and direction.
* Grid lines at the major (and, when `grid_minor` is set, minor) ticks in
  their `LineStyle`, below all items. None, or a grid colour of None,
  switches a grid level off. The kit checks colour, width and dash of the
  major grid and the colour of the minor grid; the rest is manual.
* `figure_background` only when the backend owns the whole canvas; the
  backend sets `owns_canvas` accordingly. A backend that draws into a host
  application's axes MUST NOT change the host's figure (manual).

**Legend**

* One row per entry, in the given order. The sample overlays all items of
  the entry (a cycle shows its line with a marker), styled exactly like
  the items. The kit checks the colours of each sample; widths, dashes and
  marker shapes in the samples are manual.
* Locations: the four inside corners and `"outside right"`, which MUST
  NOT cover the plot area. The kit classifies the drawn position.
* Long legend texts MAY be shortened; the legend MUST NOT squeeze the
  plot area to nothing.


## 4. Data [robustness]

* NaN or infinite coordinates split a line and drop a marker; they MUST
  NOT raise or appear in the output.
* On a log axis, values at or below zero behave like NaN.
* A log axis whose lower limit is at or below zero uses
  `upper / 1000` instead.
* A text at a non-finite position is not drawn.
* `x_limits` or `y_limits` None means autoscale over the visible items.
  Hidden items MUST NOT influence autoscaling. A zero span MUST be padded,
  never divided by.
* Empty lines and lines without a single finite point MUST be accepted.


## 5. Visibility [visibility], [removal]

* `visible=False` hides an item without removing it; hidden items do not
  take part in the legend or autoscaling.
* `describe_item` of a removed item MUST raise `KeyError`.


## 6. Read-back [read-back]

The kit can only judge what it can see, so every backend MUST implement
two methods that report what the backend *actually drew*, read from its
own objects (artists, document elements, widget state) and never copied
from the scene:

`describe_item(item_id) -> dict`, with the keys

| Kind | Keys |
|------|------|
| all | `kind` ("line", "markers", "text"), `visible`, `draw_rank` (position among visible items, bottom first) |
| line | `color` (None if the line itself is not drawn), `alpha`, `width_pt`, `dash_pt`, `cap`, `join`, `casing_color`, `casing_width_pt`, and with a casing `casing_dash_pt`, `casing_alpha`; `n_points` (points that survive the backend's own transform) |
| markers | `shape`, `size_pt` (measured from the drawn geometry), `face_color`, `edge_color`, `edge_width_pt`, `alpha`, `n_points` |
| text | `text`, `font_family`, `font_size_pt`, `font_weight`, `font_style`, `color`, `alpha`, `h_align`, `v_align`, `halo_color`, `halo_width_pt`, `screen_angle_deg` (counter-clockwise, as drawn on screen) |

`describe_axes() -> dict`, with the keys

| Group | Keys |
|-------|------|
| scales | `x_log`, `y_log`, `x_limits`, `y_limits` (as used, also when autoscaled), `plot_size_pt` (width, height of the plot area) |
| frame | `background`, `figure_background` (if `owns_canvas`), `frame_color`, `frame_width_pt` |
| ticks | `tick_direction`, `tick_color`, `tick_length_pt`, `tick_width_pt` |
| text | `x_label`, `y_label`, `title`, and for each of `x_label`, `y_label`, `title`: `<name>_font_family`, `_font_size_pt`, `_font_weight`, `_font_style`, `_color`; `tick_label_font_family`, `tick_label_font_size_pt`, `tick_label_color` |
| grid | `grid_color` (None without major grid), `grid_minor_color`, and with a major grid `grid_width_pt`, `grid_dash_pt`, `grid_lines` (count drawn), `grid_below_items` |
| legend | `legend`: list of (text, sorted sample colours), empty if none is shown; `legend_location` classified from the drawn position |

The kit uses `plot_size_pt` and the reported limits to compute where a
text direction has to point on screen, so a backend cannot pass by
rotating text in data space.

A backend with in-place updates also implements `backend_object(item_id)`,
returning its native object, so the kit can check object identity.

Reading private attributes of a library is acceptable here if there is no
public accessor; mark such places in a comment.


## 7. Output [file output], [deterministic output]

A backend that writes files declares `"file_output"`, implements
`save(path)` and sets `default_suffix`. Text formats also set
`text_output = True`.

* The same scene MUST give byte-identical files (no timestamps, no random
  ids). Use a caller-provided prefix for document-level ids so that
  several outputs can share one web page.
* Text output MUST be ASCII; escape everything else (XML character
  references in SVG).


## 8. Capabilities

Declare optional abilities in the class attribute `capabilities`:

| Name | Meaning |
|------|---------|
| `in_place_updates` | changed items keep their backend object |
| `file_output` | `save(path)` writes a file |
| `interactive` | draws into a live window or widget |
| `css_classes` | exposes item roles and groups as CSS classes |


## 9. Packaging

* The module lives in `CoolPlot/render/<name>.py` and is imported
  explicitly by users; `CoolPlot.render` never imports a backend.
* It MAY import its plotting library at module level, and MUST NOT import
  CoolProp, `CoolPlot.thermo`, `CoolPlot.diagram` or `CoolPlot.theme`;
  styles arrive resolved in the scene. `tests/test_architecture.py`
  enforces this, also for imports inside functions.
* The library is an optional extra in `setup.py`
  (`pip install coolplot[<name>]`).
* Add the backend to `tests/test_backend_conformance.py`, skipping when
  the library is not installed.


## 10. Checklist

1. Subclass `Renderer`, implement the hooks of section 1.
2. Implement every style rule of section 3, using `dash_pattern_pt` and
   points throughout.
3. Implement `describe_item`, `describe_axes` and, if applicable,
   `backend_object`.
4. `run_conformance(MyRenderer) == []`.
5. Render `examples/quickstart.py` and compare it by eye with the SVG
   and matplotlib output; the kit checks values, not appearance.
6. Add the import rule, the optional extra and the test.
