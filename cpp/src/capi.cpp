#include "coolplot/capi.h"

#include <cstring>
#include <string>

#include "coolplot/compose.h"
#include "coolplot/pdf.h"
#include "coolplot/svg.h"

namespace {

char* copy(const std::string& text) {
    char* out = new char[text.size() + 1];
    std::memcpy(out, text.c_str(), text.size() + 1);
    return out;
}

// Never throws: an error while copying the message leaves *error null.
int fail(char** error, const char* message) noexcept {
    if (error) {
        try {
            *error = copy(message);
        } catch (...) {
            *error = nullptr;
        }
    }
    return 1;
}

coolplot::SvgOptions options_of(int width, int height, const double* margins, const char* id_prefix) {
    coolplot::SvgOptions options;
    if (width > 0) options.width = width;
    if (height > 0) options.height = height;
    if (margins)
        for (int k = 0; k < 4; ++k) options.margins[k] = margins[k];
    if (id_prefix) options.id_prefix = id_prefix;
    return options;
}

coolplot::Scene parse_scene(const char* scene_json) {
    if (!scene_json) throw coolplot::Error("No scene given.");
    coolplot::json data;
    try {
        data = coolplot::json::parse(scene_json);
    } catch (const std::exception& e) {
        throw coolplot::Error(std::string("The scene is not valid JSON: ") + e.what());
    }
    return coolplot::Scene::from_json(data);
}

}  // namespace

extern "C" {

const char* coolplot_version(void) {
    return "0.1.0";
}

int coolplot_compose(const char* input_json, char** scene_json, char** error) {
    if (error) *error = nullptr;
    if (scene_json) *scene_json = nullptr;  // the output is null unless it succeeds
    if (!input_json || !scene_json) return fail(error, "No input given.");
    try {
        *scene_json = copy(coolplot::compose_json(input_json));
        return 0;
    } catch (const std::exception& e) {
        return fail(error, e.what());
    } catch (...) {
        return fail(error, "Unknown error.");
    }
}

int coolplot_scene_to_svg(const char* scene_json, int width, int height, const double* margins, const char* id_prefix, char** svg, char** error) {
    if (error) *error = nullptr;
    if (!svg) return fail(error, "No output given.");
    *svg = nullptr;
    try {
        *svg = copy(coolplot::scene_to_svg(parse_scene(scene_json), options_of(width, height, margins, id_prefix)));
        return 0;
    } catch (const std::exception& e) {
        return fail(error, e.what());
    } catch (...) {
        return fail(error, "Unknown error.");
    }
}

int coolplot_svg_plot_size_pt(const char* scene_json, int width, int height, const double* margins, double* width_pt, double* height_pt,
                              char** error) {
    if (error) *error = nullptr;
    if (!width_pt || !height_pt) return fail(error, "No output given.");
    try {
        std::pair<double, double> size = coolplot::svg_plot_size_pt(parse_scene(scene_json), options_of(width, height, margins, nullptr));
        *width_pt = size.first;
        *height_pt = size.second;
        return 0;
    } catch (const std::exception& e) {
        return fail(error, e.what());
    } catch (...) {
        return fail(error, "Unknown error.");
    }
}

int coolplot_scene_to_pdf(const char* scene_json, double width_pt, double height_pt, const double* margins_pt, const char* font_dirs,
                          char** pdf, size_t* length, char** error) {
    if (error) *error = nullptr;
    if (!pdf || !length) return fail(error, "No output given.");
    *pdf = nullptr;
    *length = 0;
    try {
        coolplot::PdfOptions options;
        if (width_pt > 0.0) options.width_pt = width_pt;
        if (height_pt > 0.0) options.height_pt = height_pt;
        if (margins_pt)
            for (int k = 0; k < 4; ++k) options.margins_pt[k] = margins_pt[k];
        if (font_dirs && *font_dirs) {
            std::string list = font_dirs;
            size_t start = 0;
            while (start <= list.size()) {
                size_t end = list.find('\n', start);
                if (end == std::string::npos) end = list.size();
                if (end > start) options.font_dirs.push_back(list.substr(start, end - start));
                start = end + 1;
            }
        }
        std::string bytes = coolplot::scene_to_pdf(parse_scene(scene_json), options);
        char* out = new char[bytes.size() + 1];
        std::memcpy(out, bytes.data(), bytes.size());
        out[bytes.size()] = '\0';
        *pdf = out;
        *length = bytes.size();
        return 0;
    } catch (const std::exception& e) {
        return fail(error, e.what());
    } catch (...) {
        return fail(error, "Unknown error.");
    }
}

void coolplot_free(char* text) {
    delete[] text;
}
}
