// The SVG writer (coolplot.render.svg.SvgRenderer, the document part).
//
// Writes the complete SVG document of a scene, byte for byte what the
// Python writer produces: every item is one element carrying its id in
// data-item and its role and group as CSS classes. Lengths: styles are in
// points, SVG user units are CSS pixels, 1 pt = 4/3 px.
#ifndef COOLPLOT_SVG_H
#define COOLPLOT_SVG_H

#include <string>
#include <vector>

#include "coolplot/scene.h"

namespace coolplot {

extern const double PX_PER_PT;

/// Round tick positions between lo and hi (major, or minor between them), coolplot.render.ticks.
std::vector<double> ticks(double lo, double hi, bool log, bool minor = false);

struct SvgOptions
{
    int width = 800;
    int height = 600;
    double margins[4] = {80.0, 20.0, 40.0, 60.0};  ///< left, right, top, bottom in px
    std::string id_prefix = "coolplot";
};

/// The SVG document of a scene, ASCII only.
std::string scene_to_svg(const Scene& scene, const SvgOptions& options = SvgOptions());

/// (width, height) of the plot area in points for a scene and options.
std::pair<double, double> svg_plot_size_pt(const Scene& scene, const SvgOptions& options = SvgOptions());

/// Escape text for XML (characters XML does not allow are dropped).
std::string xml_text(const std::string& text);
/// A quoted, escaped XML attribute value (xml.sax.saxutils.quoteattr).
std::string xml_attr(const std::string& text);
/// Non-ASCII characters as XML character references.
std::string ascii_only(const std::string& text);

}  // namespace coolplot

#endif
