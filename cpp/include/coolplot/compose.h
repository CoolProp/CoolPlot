// From computed curves to a scene (coolplot.compose.builder).
//
// compose() takes the chart spec, its calculation domain and the computed
// curves (all in SI units) and builds the scene: it converts to display
// units, resolves the theme into concrete styles, writes every text and
// places the labels. It does no property calculations.
//
// The input is one JSON record, so that any caller can hand it over:
//
//   {"spec": <chart spec>,
//    "domain": {"tp_box": [T_min, T_max, p_min, p_max], "ranges_SI": {key: [min, max]}},
//    "curves": [{"request": {"item_id", "key", "value_SI", "points", "labels"}, "curve": <curve record>}],
//    "cycles": [{"states": {"1": {key: value}}, "chains": [[{key: value}, ...]]}],
//    "plot_size_pt": [width, height] or null,
//    "previous_labels": [<text item>] or null}
#ifndef COOLPLOT_COMPOSE_H
#define COOLPLOT_COMPOSE_H

#include "coolplot/scene.h"
#include "coolplot/spec.h"

namespace coolplot {

extern const double Z_ISOLINE, Z_SATURATION, Z_LABEL, Z_PROCESS, Z_STATES;

/// The scene of a chart from the compose record above.
Scene compose(const json& input);

/// The same, from its text, as the scene record with the items in the order
/// the composer made them (scene order; a stable sort by z order gives the
/// drawing order). Errors come back as Error.
std::string compose_json(const std::string& input_text);

/// Axis title with symbol and unit, e.g. "Specific enthalpy h / kJ/kg".
std::string axis_label(const DiagramSpec& spec, const std::string& key);

/// Text of an isoline label, e.g. "T=0 deg C" or "x=0.4".
std::string label_text(const DiagramSpec& spec, const std::string& key, double value_SI, bool has_anchor = false, double anchor_SI = 0.0);

/// Estimated size of the plot area before a renderer reports the real one.
std::pair<double, double> default_plot_size_pt(const DiagramSpec& spec);

}  // namespace coolplot

#endif
