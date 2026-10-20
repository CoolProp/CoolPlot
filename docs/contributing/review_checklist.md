# Documentation review: findings and how they were closed

The review of the documentation before the road to 1.0 ({doc}`v1_review`,
section 5) found the following. Each item names what was done in 0.8.

| # | Finding | Closed by |
|---|---|---|
| 1 | No picture anywhere: README and guide start with prose | A chart on the landing page and in the README (`docs/_static/R290_ph.png`) |
| 2 | No API reference; about 40 exported names and 164 public functions without a documented home | The generated reference (`reference/api`, autosummary: one page per module with every class and function on it) |
| 3 | Docstrings use Sphinx roles that nothing renders | Sphinx with numpydoc renders them; cross references resolve |
| 4 | Public names without docstrings | About a hundred docstrings added; the build checks for missing ones (`numpydoc_validation_checks`) and `-W` fails the build |
| 5 | `INCOMP::MEG[0.3]` listed as a working fluid while every incompressible chart failed at draw | Fixed in 0.3.1; the how-to on blends and brines says what incompressibles need |
| 6 | `set_isolines("p")` in the p-h example (a quantity the diagram does not offer) | The examples use `set_lines` with quantities the diagram offers; the gallery runs them |
| 7 | `from CoolPlot import` in the styling guide | `from coolplot import`, everywhere |
| 8 | A section cross reference off by one in the user guide | The guide is split into pages; references are `{doc}` links the build checks |
| 9 | backends.md naming two backends where there are four | The backend page and the getting-started page name the four |
| 10 | A broken code span in the changelog | Rewritten in Keep-a-Changelog form |
| 11 | Computer-science vocabulary on the first screen of the README ("backend", "scene", "sync", "immutable") | The README and getting started speak of plotting libraries, pictures and updates; the terms are introduced where they are explained |
| 12 | The same vocabulary in the first screen of the user guide | The how-to pages start from the task |
| 13 | 30 lines of font-embedding detail in the tutorial | Moved to the PDF how-to; the tutorial on figures for a paper refers to it |
| 14 | No tutorials: one long guide for everything | Four tutorials (first chart, a heat pump from measurements, an air handling unit, figures for a paper) |
| 15 | How-to questions (units, labels, blends, PDF) buried in one guide | One how-to page per question |
| 16 | The design document mixes the current design with its history and the fix log | Contributing has the rules; the design document, the plan and the review are history pages |
| 17 | No explanation of what a change costs | `explanation/what_a_change_costs` |
| 18 | The colour choices (CVD check) explained only in the styling guide's middle | `explanation/colours` |
| 19 | The numerics undocumented for users | `explanation/numerics` (short) and the design document, section 11 (long) |
| 20 | No list of what is not supported | `explanation/not_supported` |
| 21 | The tables of diagram types, units and presets written by hand and stale | Generated at build time from the package (`reference/tables`) |
| 22 | Examples not run by any documentation build | sphinx-gallery runs every example at build time and shows its output |
| 23 | No Read the Docs configuration, no docs job in CI | `.readthedocs.yaml`, the `docs` job of the tests workflow (`sphinx-build -W`) |
| 24 | No upgrade guide for the legacy API and the renamed verbs | `upgrade` |
