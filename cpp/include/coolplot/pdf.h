// The PDF writer: a scene as one print-ready page with TrueType fonts
// embedded as subsets (coolplot.render.base: the "pdf_output" capability).
//
// The page is drawn like the SVG document, in points: background, grid,
// the items in drawing order (clipped to the plot area), the frame, ticks
// and tick labels, axis titles, the title and the legend. Colours are
// sRGB, every text is real text with a ToUnicode map, and the same scene
// gives the same bytes (no dates, no file identifier).
#ifndef COOLPLOT_PDF_H
#define COOLPLOT_PDF_H

#include <string>
#include <vector>

#include "coolplot/scene.h"

namespace coolplot {

struct PdfOptions
{
    double width_pt = 576.0;
    double height_pt = 432.0;
    double margins_pt[4] = {60.0, 15.0, 30.0, 45.0};  ///< left, right, top, bottom
    std::vector<std::string> font_dirs;                 ///< empty: the platform's font directories
    std::vector<std::string> font_files;                ///< font files registered before the directories are searched
    bool compress = true;                               ///< Flate compress the streams when zlib is available
    std::string producer = "coolplot-core";
};

/// The PDF file of a scene, as bytes in a string.
std::string scene_to_pdf(const Scene& scene, const PdfOptions& options = PdfOptions());

/// (width, height) of the plot area in points for a scene and options.
std::pair<double, double> pdf_plot_size_pt(const Scene& scene, const PdfOptions& options = PdfOptions());

}  // namespace coolplot

#endif
