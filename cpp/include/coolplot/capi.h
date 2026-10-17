// The C ABI of coolplot-core: a few functions, strings in and out, so any
// language can call it. Every output string is allocated by the library and
// freed with coolplot_free. A failure returns 1 and an error text in *error.
#ifndef COOLPLOT_CAPI_H
#define COOLPLOT_CAPI_H

#if defined(_WIN32) && defined(COOLPLOT_CORE_SHARED)
#    define COOLPLOT_EXPORT __declspec(dllexport)
#else
#    define COOLPLOT_EXPORT
#endif

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/// The library version, a static string.
COOLPLOT_EXPORT const char* coolplot_version(void);

/// The scene JSON of a chart from the compose record (see coolplot/compose.h).
COOLPLOT_EXPORT int coolplot_compose(const char* input_json, char** scene_json, char** error);

/// The SVG document of a scene JSON. margins are (left, right, top, bottom) in px, or NULL for the defaults.
COOLPLOT_EXPORT int coolplot_scene_to_svg(const char* scene_json, int width, int height, const double* margins, const char* id_prefix, char** svg,
                                          char** error);

/// The (width, height) of the plot area in points for a scene and the SVG options.
COOLPLOT_EXPORT int coolplot_svg_plot_size_pt(const char* scene_json, int width, int height, const double* margins, double* width_pt,
                                              double* height_pt, char** error);

/// The PDF file of a scene JSON: `pdf` gets the bytes (also NUL terminated) and `length` their number.
/// margins_pt are (left, right, top, bottom) or NULL for the defaults; font_dirs lists directories
/// separated by newlines, or NULL/empty for the platform's.
COOLPLOT_EXPORT int coolplot_scene_to_pdf(const char* scene_json, double width_pt, double height_pt, const double* margins_pt,
                                          const char* font_dirs, char** pdf, size_t* length, char** error);

/// Free a string the library returned.
COOLPLOT_EXPORT void coolplot_free(char* text);

#ifdef __cplusplus
}
#endif

#endif
