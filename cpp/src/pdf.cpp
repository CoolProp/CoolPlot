#include "coolplot/pdf.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <sstream>

#include "coolplot/svg.h"
#include "coolplot/truetype.h"

#ifdef COOLPLOT_HAVE_ZLIB
#    include <zlib.h>
#endif

namespace coolplot {

namespace {

const double PI = 3.14159265358979323846;
const double KAPPA = 0.5522847498;  // circle from four Bezier arcs

std::string num(double value) {
    if (!std::isfinite(value)) throw Error("Non-finite value in PDF output.");
    std::string text = fixed_text(value, 4);  // locale-free, always has a decimal point
    while (!text.empty() && text.back() == '0') text.pop_back();
    if (!text.empty() && text.back() == '.') text.pop_back();
    return (text == "-0" || text.empty()) ? "0" : text;
}

std::string color_ops(const Color& color, bool stroke) {
    int r = std::stoi(color.hex.substr(1, 2), nullptr, 16), g = std::stoi(color.hex.substr(3, 2), nullptr, 16),
        b = std::stoi(color.hex.substr(5, 2), nullptr, 16);
    return num(r / 255.0) + " " + num(g / 255.0) + " " + num(b / 255.0) + (stroke ? " RG\n" : " rg\n");
}

/// A PDF text string: plain ASCII in parentheses, anything else as UTF-16 hex.
std::string pdf_string(const std::string& text) {
    bool ascii = true;
    for (char c : text)
        if (static_cast<unsigned char>(c) >= 0x80) ascii = false;
    if (ascii) {
        std::string out = "(";
        for (char c : text) {
            if (c == '\\' || c == '(' || c == ')') out += '\\';
            out += c;
        }
        return out + ")";
    }
    std::string out = "<FEFF";
    size_t i = 0;
    while (i < text.size()) {
        unsigned char c = static_cast<unsigned char>(text[i]);
        unsigned long cp;
        int extra = c < 0x80 ? 0 : (c & 0xE0) == 0xC0 ? 1 : (c & 0xF0) == 0xE0 ? 2 : 3;
        cp = extra == 0 ? c : extra == 1 ? (c & 0x1F) : extra == 2 ? (c & 0x0F) : (c & 0x07);
        ++i;
        for (int k = 0; k < extra && i < text.size(); ++k, ++i) cp = (cp << 6) | (static_cast<unsigned char>(text[i]) & 0x3F);
        char buffer[16];
        if (cp >= 0x10000) {
            cp -= 0x10000;
            std::snprintf(buffer, sizeof(buffer), "%04lX%04lX", 0xD800 + (cp >> 10), 0xDC00 + (cp & 0x3FF));
        } else {
            std::snprintf(buffer, sizeof(buffer), "%04lX", cp);
        }
        out += buffer;
    }
    return out + ">";
}

std::vector<unsigned long> code_points(const std::string& text) {
    std::vector<unsigned long> out;
    size_t i = 0;
    while (i < text.size()) {
        unsigned char c = static_cast<unsigned char>(text[i]);
        int extra = c < 0x80 ? 0 : (c & 0xE0) == 0xC0 ? 1 : (c & 0xF0) == 0xE0 ? 2 : 3;
        unsigned long cp = extra == 0 ? c : extra == 1 ? (c & 0x1F) : extra == 2 ? (c & 0x0F) : (c & 0x07);
        ++i;
        for (int k = 0; k < extra && i < text.size(); ++k, ++i) cp = (cp << 6) | (static_cast<unsigned char>(text[i]) & 0x3F);
        out.push_back(cp);
    }
    return out;
}

std::string read_file(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in.good()) throw Error("Cannot read the font file " + path + ".");
    std::stringstream buffer;
    buffer << in.rdbuf();
    return buffer.str();
}

/// One font used in the document: the file, the glyphs used and the code points behind them.
struct UsedFont
{
    std::string path;
    std::shared_ptr<TrueTypeFont> font;
    std::set<int> glyphs;
    std::map<int, unsigned long> unicode;  // glyph -> code point, for the ToUnicode map
    std::string resource;                  // /F1, /F2, ...
};

// The index of the font directories, built once per process and set of
// directories (scanning them takes long). Writers in several threads (the C
// ABI and the Python module, which releases the GIL) share it, so the cache
// is locked; an index is only read after it is built, and a std::map keeps
// its entries in place, so the reference stays valid after the lock.
const FontIndex& font_index(const PdfOptions& options) {
    static std::map<std::string, std::shared_ptr<FontIndex>> cache;
    static std::mutex mutex;
    std::vector<std::string> dirs = options.font_dirs.empty() ? FontIndex::default_dirs() : options.font_dirs;
    std::string key;
    for (const std::string& d : dirs) key += d + "\n";
    key += "--\n";
    for (const std::string& f : options.font_files) key += f + "\n";
    std::lock_guard<std::mutex> lock(mutex);
    auto found = cache.find(key);
    if (found == cache.end()) found = cache.emplace(key, std::make_shared<FontIndex>(dirs, options.font_files)).first;
    return *found->second;
}

class Writer
{
   public:
    Writer(const Scene& scene, const PdfOptions& options) : scene_(scene), options_(options), index_(font_index(options)) {
        legend_entries_ = scene.legend_entries();
        Range x = scene.axes.has_x_limits ? scene.axes.x_limits : data_limits(true, scene.axes.x_log);
        Range y = scene.axes.has_y_limits ? scene.axes.y_limits : data_limits(false, scene.axes.y_log);
        x = drawable_limits(x, scene.axes.x_log);
        y = drawable_limits(y, scene.axes.y_log);
        x0_ = x.lo;
        x1_ = x.hi;
        y0_ = y.lo;
        y1_ = y.hi;
        // Text that may leave the frame and sits on its edge widens that margin,
        // the same way as in the SVG writer, so that both give the same plot size
        extra_margins_ = unclipped_margins();
        double left = options.margins_pt[0] + extra_margins_[0], right = options.margins_pt[1] + extra_margins_[1];
        double top = options.margins_pt[2] + extra_margins_[2], bottom = options.margins_pt[3] + extra_margins_[3];
        if (scene.axes.style.legend.location == "outside right") {
            double width = legend_size().first;
            if (!is_zero(width)) right += width + 9.0;
        }
        bw_ = std::max(options.width_pt - left - right, 0.25 * options.width_pt);
        bh_ = std::max(options.height_pt - top - bottom, 0.25 * options.height_pt);
        bx_ = left;
        by_ = bottom;
    }

    std::pair<double, double> plot_size_pt() const {
        return {bw_, bh_};
    }

    std::string document() {
        std::string content = page_content();
        // Objects: 1 catalog, 2 pages, 3 page, 4 content, 5 info, then per font: Type0, CIDFont, descriptor, file, ToUnicode
        std::vector<std::string> objects;
        objects.push_back("<< /Type /Catalog /Pages 2 0 R >>");
        objects.push_back("<< /Type /Pages /Kids [3 0 R] /Count 1 >>");
        std::string fonts_resource, states_resource;
        int next = 6;
        std::vector<std::string> font_objects;
        for (UsedFont& f : fonts_) {
            fonts_resource += " " + f.resource + " " + std::to_string(next) + " 0 R";
            std::vector<std::string> made = font_objects_of(f, next);
            next += static_cast<int>(made.size());
            font_objects.insert(font_objects.end(), made.begin(), made.end());
        }
        for (const auto& kv : states_)
            states_resource += " /" + kv.second + " << /Type /ExtGState /CA " + num(kv.first.first) + " /ca " + num(kv.first.second) + " >>";
        objects.push_back("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 " + num(options_.width_pt) + " " + num(options_.height_pt)
                          + "] /Resources << /ProcSet [/PDF /Text] /Font <<" + fonts_resource + " >> /ExtGState <<" + states_resource
                          + " >> >> /Contents 4 0 R >>");
        objects.push_back(stream(content, ""));
        std::string info = "<< /Producer " + pdf_string(options_.producer);
        if (!scene_.axes.title.empty()) info += " /Title " + pdf_string(scene_.axes.title);
        objects.push_back(info + " >>");
        objects.insert(objects.end(), font_objects.begin(), font_objects.end());
        std::string out = "%PDF-1.4\n%\xE2\xE3\xCF\xD3\n";
        std::vector<size_t> offsets;
        for (size_t i = 0; i < objects.size(); ++i) {
            offsets.push_back(out.size());
            out += std::to_string(i + 1) + " 0 obj\n" + objects[i] + "\nendobj\n";
        }
        size_t xref = out.size();
        out += "xref\n0 " + std::to_string(objects.size() + 1) + "\n0000000000 65535 f \n";
        for (size_t offset : offsets) {
            char line[32];
            std::snprintf(line, sizeof(line), "%010zu 00000 n \n", offset);
            out += line;
        }
        out += "trailer\n<< /Size " + std::to_string(objects.size() + 1) + " /Root 1 0 R /Info 5 0 R >>\nstartxref\n" + std::to_string(xref)
               + "\n%%EOF\n";
        return out;
    }

   private:
    const Scene& scene_;
    const PdfOptions& options_;
    const FontIndex& index_;
    std::vector<std::pair<std::string, std::vector<size_t>>> legend_entries_;
    std::array<double, 4> extra_margins_ = {0.0, 0.0, 0.0, 0.0};  // left, right, top, bottom in pt
    double x0_ = 0.0, x1_ = 1.0, y0_ = 0.0, y1_ = 1.0;
    double bx_ = 0.0, by_ = 0.0, bw_ = 1.0, bh_ = 1.0;
    std::vector<UsedFont> fonts_;
    // The font files a text style names, indexed once per document: every
    // tick label and isoline label asks for its font
    std::map<std::vector<std::string>, std::unique_ptr<FontIndex>> file_indexes_;
    std::map<std::pair<double, double>, std::string> states_;  // (CA, ca) -> name

    const FontIndex& file_index(const std::vector<std::string>& files) {
        std::unique_ptr<FontIndex>& index = file_indexes_[files];
        if (!index) index = std::make_unique<FontIndex>(std::vector<std::string>{}, files);
        return *index;
    }

    // Streams -------------------------------------------------------------
    std::string stream(const std::string& data, const std::string& extra) const {
        std::string body = data;
        std::string filter;
#ifdef COOLPLOT_HAVE_ZLIB
        if (options_.compress) {
            uLongf size = compressBound(static_cast<uLong>(data.size()));
            std::string packed(size, '\0');
            if (compress2(reinterpret_cast<Bytef*>(&packed[0]), &size, reinterpret_cast<const Bytef*>(data.data()),
                          static_cast<uLong>(data.size()), 9)
                == Z_OK) {
                packed.resize(size);
                body = packed;
                filter = " /Filter /FlateDecode";
            }
        }
#endif
        return "<< /Length " + std::to_string(body.size()) + filter + extra + " >>\nstream\n" + body + "\nendstream";
    }

    // Geometry -------------------------------------------------------------
    Range data_limits(bool x_axis, bool log) const {
        double lo = HUGE_VAL, hi = -HUGE_VAL;
        bool any = false;
        for (const Item& item : scene_.items) {
            if (!item.visible || item.type == ItemType::Text) continue;
            for (double v : x_axis ? item.x : item.y) {
                if (!std::isfinite(v) || (log && !(v > 0.0))) continue;
                lo = std::min(lo, v);
                hi = std::max(hi, v);
                any = true;
            }
        }
        if (!any) return log ? Range{1.0, 10.0} : Range{0.0, 1.0};
        return {lo, hi};
    }

    static double fraction(double v, double lo, double hi, bool log) {
        if (!std::isfinite(v)) return std::nan("");
        if (log) return v > 0 ? (std::log10(v) - std::log10(lo)) / (std::log10(hi) - std::log10(lo)) : std::nan("");
        return (v - lo) / (hi - lo);
    }
    double px(double x) const {
        return bx_ + fraction(x, x0_, x1_, scene_.axes.x_log) * bw_;
    }
    double py(double y) const {
        return by_ + fraction(y, y0_, y1_, scene_.axes.y_log) * bh_;
    }

    // Fonts -----------------------------------------------------------------
    UsedFont& font_for(const Font& request) {
        std::string family_used;
        std::string path;
        if (!request.files.empty()) {
            path = file_index(request.files).find(request.family, request.weight == "bold", request.style == "italic",
                                                  &family_used);
        }
        if (path.empty()) path = index_.find(request.family, request.weight == "bold", request.style == "italic", &family_used);
        if (path.empty()) {
            std::string names;
            for (const std::string& f : request.family) names += (names.empty() ? "" : ", ") + f;
            throw Error("No TrueType font found for the families " + names + "; install one (DejaVu Sans, Liberation Sans) or give a font file.");
        }
        for (UsedFont& f : fonts_)
            if (f.path == path) return f;
        UsedFont used;
        used.path = path;
        used.font = std::make_shared<TrueTypeFont>(read_file(path));
        used.resource = "/F" + std::to_string(fonts_.size() + 1);
        fonts_.push_back(used);
        return fonts_.back();
    }

    std::vector<std::string> font_objects_of(UsedFont& f, int first) const {
        const TrueTypeFont& font = *f.font;
        double scale = 1000.0 / font.units_per_em();
        std::string name = "COOLPL+" + font.postscript_name();
        std::string widths;
        for (int g : f.glyphs) widths += " " + std::to_string(g) + " [" + num(font.advance(g) * scale) + "]";
        int flags = 32 + (font.italic() ? 64 : 0);
        std::string descriptor = "<< /Type /FontDescriptor /FontName /" + name + " /Flags " + std::to_string(flags) + " /FontBBox ["
                                 + num(font.x_min() * scale) + " " + num(font.y_min() * scale) + " " + num(font.x_max() * scale) + " "
                                 + num(font.y_max() * scale) + "] /ItalicAngle " + num(font.italic_angle()) + " /Ascent "
                                 + num(font.ascent() * scale) + " /Descent " + num(font.descent() * scale) + " /CapHeight "
                                 + num(font.cap_height() * scale) + " /StemV " + (font.bold() ? "120" : "80") + " /FontFile2 "
                                 + std::to_string(first + 3) + " 0 R >>";
        std::string program = font.subset(f.glyphs);
        std::string cmap = "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) "
                           "/Supplement 0 >> def\n/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n1 begincodespacerange\n<0000> <FFFF>\n"
                           "endcodespacerange\n";
        std::vector<std::pair<int, unsigned long>> pairs(f.unicode.begin(), f.unicode.end());
        for (size_t i = 0; i < pairs.size(); i += 100) {
            size_t n = std::min<size_t>(100, pairs.size() - i);
            cmap += std::to_string(n) + " beginbfchar\n";
            for (size_t k = i; k < i + n; ++k) {
                char line[40];
                unsigned long cp = pairs[k].second;
                if (cp >= 0x10000) {
                    cp -= 0x10000;
                    std::snprintf(line, sizeof(line), "<%04X> <%04lX%04lX>\n", pairs[k].first, 0xD800 + (cp >> 10), 0xDC00 + (cp & 0x3FF));
                } else {
                    std::snprintf(line, sizeof(line), "<%04X> <%04lX>\n", pairs[k].first, cp);
                }
                cmap += line;
            }
            cmap += "endbfchar\n";
        }
        cmap += "endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n";
        return {"<< /Type /Font /Subtype /Type0 /BaseFont /" + name + " /Encoding /Identity-H /DescendantFonts [" + std::to_string(first + 1)
                  + " 0 R] /ToUnicode " + std::to_string(first + 4) + " 0 R >>",
                "<< /Type /Font /Subtype /CIDFontType2 /BaseFont /" + name
                  + " /CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> /FontDescriptor " + std::to_string(first + 2)
                  + " 0 R /DW 1000 /W [" + widths + " ] /CIDToGIDMap /Identity >>",
                descriptor, stream(program, " /Length1 " + std::to_string(program.size())), stream(cmap, "")};
    }

    std::string state_for(double stroke_alpha, double fill_alpha) {
        std::pair<double, double> key = {stroke_alpha, fill_alpha};
        auto found = states_.find(key);
        if (found == states_.end()) found = states_.emplace(key, "GS" + std::to_string(states_.size() + 1)).first;
        return "/" + found->second + " gs\n";
    }

    // Drawing ---------------------------------------------------------------
    static std::string stroke_style(const Color& color, double width_pt, const std::vector<double>& dash, const std::string& cap,
                                    const std::string& join) {
        std::string out = color_ops(color, true) + num(width_pt) + " w " + (cap == "round" ? "1" : cap == "square" ? "2" : "0") + " J "
                          + (join == "round" ? "1" : join == "bevel" ? "2" : "0") + " j\n";
        if (dash.empty()) {
            out += "[] 0 d\n";
        } else {
            out += "[";
            for (double d : dash) out += " " + num(d);
            out += " ] 0 d\n";
        }
        return out;
    }

    std::string path_of(const Item& item) const {
        std::string d;
        bool pen_down = false;
        for (size_t i = 0; i < item.x.size(); ++i) {
            double x = px(item.x[i]), y = py(item.y[i]);
            if (!(std::isfinite(x) && std::isfinite(y))) {
                pen_down = false;
                continue;
            }
            d += num(x) + " " + num(y) + (pen_down ? " l\n" : " m\n");
            pen_down = true;
        }
        return d;
    }

    std::string clip_to_plot() const {
        return num(bx_) + " " + num(by_) + " " + num(bw_) + " " + num(bh_) + " re W n\n";
    }

    std::string line(const Item& item) {
        const LineStyle& s = item.line_style;
        std::string path = path_of(item);
        if (path.empty()) return "";
        std::vector<double> dash = dash_pattern_pt(s.dash, s.width_pt);
        std::string out = "q\n" + clip_to_plot() + state_for(s.alpha, s.alpha);
        if (s.casing_color.present && s.casing_width_pt > 0.0)
            out += stroke_style(s.casing_color, s.width_pt + 2.0 * s.casing_width_pt, dash, s.cap, s.join) + path + "S\n";
        if (s.color.present) out += stroke_style(s.color, s.width_pt, dash, s.cap, s.join) + path + "S\n";
        return out + "Q\n";
    }

    static std::string marker_path(const std::string& shape, double x, double y, double r) {
        auto p = [](double a, double b) { return num(a) + " " + num(b); };
        if (shape == "o") {
            double k = KAPPA * r;
            return p(x + r, y) + " m\n" + p(x + r, y + k) + " " + p(x + k, y + r) + " " + p(x, y + r) + " c\n" + p(x - k, y + r) + " "
                   + p(x - r, y + k) + " " + p(x - r, y) + " c\n" + p(x - r, y - k) + " " + p(x - k, y - r) + " " + p(x, y - r) + " c\n"
                   + p(x + k, y - r) + " " + p(x + r, y - k) + " " + p(x + r, y) + " c\nh\n";
        }
        if (shape == "s") return p(x - r, y - r) + " " + num(2 * r) + " " + num(2 * r) + " re\n";
        std::vector<std::pair<double, double>> points;
        if (shape == "^")
            points = {{0, r}, {r, -r}, {-r, -r}};  // y up: the tip is at the top
        else if (shape == "v")
            points = {{0, -r}, {r, r}, {-r, r}};
        else if (shape == "D")
            points = {{0, r}, {r, 0}, {0, -r}, {-r, 0}};
        if (!points.empty()) {
            std::string d;
            for (size_t i = 0; i < points.size(); ++i) d += p(x + points[i].first, y + points[i].second) + (i ? " l\n" : " m\n");
            return d + "h\n";
        }
        if (shape == "x") return p(x - r, y - r) + " m " + p(x + r, y + r) + " l\n" + p(x - r, y + r) + " m " + p(x + r, y - r) + " l\n";
        if (shape == "+") return p(x - r, y) + " m " + p(x + r, y) + " l\n" + p(x, y - r) + " m " + p(x, y + r) + " l\n";
        throw Error("Unknown marker shape '" + shape + "'.");
    }

    std::string markers(const Item& item) {
        const MarkerStyle& s = item.marker_style;
        double r = s.size_pt / 2.0;
        bool open = s.shape == "x" || s.shape == "+";
        bool fill = !open && s.face_color.present, stroke = s.edge_color.present && s.edge_width_pt > 0.0;
        std::string op = fill && stroke ? "B" : fill ? "f" : stroke ? "S" : "n";
        std::string out = "q\n" + clip_to_plot() + state_for(s.alpha, s.alpha);
        if (fill) out += color_ops(s.face_color, false);
        if (stroke) out += stroke_style(s.edge_color, s.edge_width_pt, {}, "butt", "miter");
        for (size_t i = 0; i < item.x.size(); ++i) {
            double x = px(item.x[i]), y = py(item.y[i]);
            if (std::isfinite(x) && std::isfinite(y)) out += marker_path(s.shape, x, y, r) + op + "\n";
        }
        return out + "Q\n";
    }

    /// Text at (x, y) in points: aligned, rotated by angle_deg, with a halo, inside the clip when asked.
    std::string text_at(const std::string& text, const TextStyle& style, double x, double y, double angle_deg, bool clip) {
        if (text.empty()) return "";
        UsedFont& f = font_for(style.font);
        const TrueTypeFont& font = *f.font;
        double size = style.font.size_pt, scale = size / font.units_per_em();
        std::string glyphs;
        double width = 0.0;
        for (unsigned long cp : code_points(text)) {
            int g = font.glyph_of(cp);
            unsigned long shown = cp;  // what a reader gets back when copying the text
            if (g == 0 && cp != 0x20) {
                g = font.glyph_of('?');  // a character the font lacks is drawn and read as "?"
                shown = '?';
            }
            f.glyphs.insert(g);
            if (!f.unicode.count(g)) f.unicode[g] = shown;
            char hex[8];
            std::snprintf(hex, sizeof(hex), "%04X", g);
            glyphs += hex;
            width += font.advance(g) * scale;
        }
        double ascent = font.ascent() * scale, descent = -font.descent() * scale;
        double dx = style.h_align == "left" ? 0.0 : style.h_align == "center" ? -width / 2.0 : -width;
        double dy = style.v_align == "bottom" ? descent : style.v_align == "center" ? -(ascent - descent) / 2.0 : -ascent;
        double c = std::cos(angle_deg * PI / 180.0), s = std::sin(angle_deg * PI / 180.0);
        std::string matrix = num(c) + " " + num(s) + " " + num(-s) + " " + num(c) + " " + num(x + dx * c - dy * s) + " " + num(y + dx * s + dy * c);
        std::string out = "q\n";
        if (clip) out += clip_to_plot();
        out += state_for(style.alpha, style.alpha);
        // The halo is the same text stroked underneath, in a text block of its
        // own, so that a reader finds each text once per block
        if (style.halo_color.present && style.halo_width_pt > 0.0)
            out += "BT\n" + f.resource + " " + num(size) + " Tf\n1 Tr " + color_ops(style.halo_color, true) + num(2.0 * style.halo_width_pt)
                   + " w 1 j 1 J\n" + matrix + " Tm <" + glyphs + "> Tj\nET\n";
        out += "BT\n" + f.resource + " " + num(size) + " Tf\n0 Tr " + (style.color.present ? color_ops(style.color, false) : std::string("0 g\n"))
               + matrix + " Tm <" + glyphs + "> Tj\nET\nQ\n";
        return out;
    }

    double angle_of(const Item& item, double x, double y) const {
        if (!item.has_direction) return 0.0;
        double step = 1e-3;
        double qx = px(item.text_x + item.direction_x * step), qy = py(item.text_y + item.direction_y * step);
        if (!(std::isfinite(qx) && std::isfinite(qy)) || (same_number(qx, x) && same_number(qy, y))) return 0.0;
        double angle = std::atan2(qy - y, qx - x) * 180.0 / PI;
        if (angle > 90.0) return angle - 180.0;
        if (angle <= -90.0) return angle + 180.0;
        return angle;
    }

    std::string text(const Item& item) {
        if (!(std::isfinite(item.text_x) && std::isfinite(item.text_y))) return "";
        double x = px(item.text_x), y = py(item.text_y);
        if (!(std::isfinite(x) && std::isfinite(y))) return "";
        return text_at(item.text, item.text_style, x + item.offset_x_pt, y + item.offset_y_pt, angle_of(item, x, y), item.clip);
    }

    /// (left, right, down, up) reach of a text from its anchor in pt, from its length and alignment.
    static void text_extent_pt(const Item& item, double& left, double& right, double& down, double& up) {
        double size = item.text_style.font.size_pt;
        double length = 0.6 * size * text_length(item.text), height = 1.25 * size;
        bool vertical = item.has_direction && std::fabs(item.direction_y) > std::fabs(item.direction_x);
        const std::string& h = item.text_style.h_align;
        const std::string& v = item.text_style.v_align;
        double along0 = h == "left" ? 0.0 : h == "center" ? length / 2 : length;
        double along1 = h == "left" ? length : h == "center" ? length / 2 : 0.0;
        double across0 = v == "bottom" ? 0.0 : v == "center" ? height / 2 : height;
        double across1 = v == "bottom" ? height : v == "center" ? height / 2 : 0.0;
        if (vertical) {  // reads upwards: its start is at the bottom
            left = across1;
            right = across0;
            down = along0;
            up = along1;
        } else {
            left = along0;
            right = along1;
            down = across0;
            up = across1;
        }
    }

    /// Extra (left, right, top, bottom) margins in pt for text outside the frame.
    std::array<double, 4> unclipped_margins() const {
        std::array<double, 4> need = {0.0, 0.0, 0.0, 0.0};
        for (const Item& item : scene_.items) {
            if (!(item.type == ItemType::Text && item.visible && !item.clip)) continue;
            double fx = fraction(item.text_x, x0_, x1_, scene_.axes.x_log), fy = fraction(item.text_y, y0_, y1_, scene_.axes.y_log);
            if (!(std::isfinite(fx) && std::isfinite(fy))) continue;
            double left, right, down, up;
            text_extent_pt(item, left, right, down, up);
            double dx = item.offset_x_pt, dy = item.offset_y_pt;
            double reach[4] = {left - dx + 3.0, right + dx + 3.0, up + dy + 3.0, down - dy + 3.0};
            bool touches[4] = {fx <= 1e-9, fx >= 1.0 - 1e-9, fy >= 1.0 - 1e-9, fy <= 1e-9};
            for (int k = 0; k < 4; ++k) need[k] = std::max(need[k], touches[k] ? reach[k] : 0.0);
        }
        for (int k = 0; k < 4; ++k) {
            // With a title the configured top margin holds the title, so labels
            // above the frame need their whole height on top of it (as in the SVG writer)
            if (k == 2 && !scene_.axes.title.empty()) continue;
            need[k] = std::max(0.0, need[k] - options_.margins_pt[k]);
        }
        return need;
    }

    /// Longest legend text in characters before it is cut with "...", as in the SVG writer.
    int legend_chars() const {
        double size = scene_.axes.style.legend.text.font.size_pt;
        return std::max(4, static_cast<int>((0.4 * options_.width_pt - 33.0) / (0.6 * size)));
    }

    std::string legend_text(const std::string& text) const {
        size_t limit = static_cast<size_t>(legend_chars());
        return text_length(text) <= limit ? text : text_prefix(text, limit - 3) + "...";
    }

    std::pair<double, double> legend_size() const {
        const LegendStyle& st = scene_.axes.style.legend;
        if (!st.visible || legend_entries_.empty()) return {0.0, 0.0};
        double size = st.text.font.size_pt;
        size_t longest = 0;
        for (const auto& entry : legend_entries_) longest = std::max(longest, text_length(legend_text(entry.first)));
        return {33.0 + 0.6 * size * longest, 6.0 + 1.6 * size * legend_entries_.size()};
    }

    std::string legend() {
        const LegendStyle& st = scene_.axes.style.legend;
        std::pair<double, double> size = legend_size();
        if (is_zero(size.first)) return "";
        double pad = 6.0;
        double x = st.location == "upper left" || st.location == "lower left" ? bx_ + pad
                   : st.location == "outside right"                            ? bx_ + bw_ + 9.0
                                                                                : bx_ + bw_ - pad - size.first;
        bool upper = st.location == "upper left" || st.location == "upper right" || st.location == "outside right";
        double top = upper ? by_ + bh_ - pad : by_ + pad + size.second;
        std::string out = "q\n";
        if (st.background.present || st.frame_color.present) {
            if (st.background.present) out += color_ops(st.background, false);
            if (st.frame_color.present) out += stroke_style(st.frame_color, 0.5, {}, "butt", "miter");
            out += num(x) + " " + num(top - size.second) + " " + num(size.first) + " " + num(size.second) + " re "
                   + (st.background.present && st.frame_color.present ? "B" : st.background.present ? "f" : "S") + "\n";
        }
        double font_size = st.text.font.size_pt;
        for (size_t i = 0; i < legend_entries_.size(); ++i) {
            double cy = top - 3.0 - font_size * (1.6 * i + 0.8);
            for (size_t index : legend_entries_[i].second) {
                const Item& item = scene_.items[index];
                if (item.type == ItemType::Line) {
                    const LineStyle& s = item.line_style;
                    std::vector<double> dash = dash_pattern_pt(s.dash, s.width_pt);
                    std::string seg = num(x + 4.5) + " " + num(cy) + " m " + num(x + 21.0) + " " + num(cy) + " l S\n";
                    out += "q\n" + state_for(s.alpha, s.alpha);
                    if (s.casing_color.present && s.casing_width_pt > 0.0)
                        out += stroke_style(s.casing_color, s.width_pt + 2.0 * s.casing_width_pt, dash, s.cap, s.join) + seg;
                    if (s.color.present) out += stroke_style(s.color, s.width_pt, dash, s.cap, s.join) + seg;
                    out += "Q\n";
                } else if (item.type == ItemType::Markers) {
                    const MarkerStyle& s = item.marker_style;
                    bool open = s.shape == "x" || s.shape == "+";
                    bool fill = !open && s.face_color.present, stroke = s.edge_color.present && s.edge_width_pt > 0.0;
                    out += "q\n" + state_for(s.alpha, s.alpha);
                    if (fill) out += color_ops(s.face_color, false);
                    if (stroke) out += stroke_style(s.edge_color, s.edge_width_pt, {}, "butt", "miter");
                    out += marker_path(s.shape, x + 12.75, cy, s.size_pt / 2.0) + (fill && stroke ? "B" : fill ? "f" : stroke ? "S" : "n") + "\nQ\n";
                }
            }
            TextStyle style = st.text;
            style.h_align = "left";
            style.v_align = "center";
            out += text_at(legend_text(legend_entries_[i].first), style, x + 25.5, cy, 0.0, false);
        }
        return out + "Q\n";
    }

    std::string page_content() {
        const AxesSpec& axes = scene_.axes;
        const AxesStyle& st = axes.style;
        std::string out;
        if (st.figure_background.present)
            out += color_ops(st.figure_background, false) + "0 0 " + num(options_.width_pt) + " " + num(options_.height_pt) + " re f\n";
        if (st.background.present) out += color_ops(st.background, false) + num(bx_) + " " + num(by_) + " " + num(bw_) + " " + num(bh_) + " re f\n";
        // Grid
        for (int level = 0; level < 2; ++level) {
            bool minor = level == 0;
            if (minor ? !st.has_grid_minor : !st.has_grid_major) continue;
            const LineStyle& g = minor ? st.grid_minor : st.grid_major;
            if (!g.color.present) continue;
            out += "q\n" + state_for(g.alpha, g.alpha) + stroke_style(g.color, g.width_pt, dash_pattern_pt(g.dash, g.width_pt), g.cap, g.join);
            for (double value : ticks(x0_, x1_, axes.x_log, minor))
                out += num(px(value)) + " " + num(by_) + " m " + num(px(value)) + " " + num(by_ + bh_) + " l S\n";
            for (double value : ticks(y0_, y1_, axes.y_log, minor))
                out += num(bx_) + " " + num(py(value)) + " m " + num(bx_ + bw_) + " " + num(py(value)) + " l S\n";
            out += "Q\n";
        }
        // Items in drawing order
        for (size_t i : scene_.draw_order()) {
            const Item& item = scene_.items[i];
            if (!item.visible) continue;
            if (item.type == ItemType::Line)
                out += line(item);
            else if (item.type == ItemType::Markers)
                out += markers(item);
            else
                out += text(item);
        }
        // Frame, ticks and labels
        if (st.frame_color.present && st.frame_width_pt > 0.0)
            out += "q\n" + stroke_style(st.frame_color, st.frame_width_pt, {}, "butt", "miter") + num(bx_) + " " + num(by_) + " " + num(bw_) + " "
                   + num(bh_) + " re S\nQ\n";
        double length = st.tick_length_pt * (st.tick_direction == "out" ? 1.0 : -1.0);
        double gap = st.tick_direction == "out" ? std::fabs(length) : 0.0;
        if (st.tick_color.present && st.tick_width_pt > 0.0) out += "q\n" + stroke_style(st.tick_color, st.tick_width_pt, {}, "butt", "miter");
        std::string tick_labels;
        TextStyle tick_style = st.tick_label;
        for (double value : ticks(x0_, x1_, axes.x_log)) {
            double x = px(value);
            if (st.tick_color.present && st.tick_width_pt > 0.0) out += num(x) + " " + num(by_) + " m " + num(x) + " " + num(by_ - length) + " l S\n";
            tick_style.h_align = "center";
            tick_style.v_align = "top";
            tick_labels += text_at(format_number(value, axes.tick_digits), tick_style, x, by_ - gap - 2.25, 0.0, false);
        }
        for (double value : ticks(y0_, y1_, axes.y_log)) {
            double y = py(value);
            if (st.tick_color.present && st.tick_width_pt > 0.0) out += num(bx_) + " " + num(y) + " m " + num(bx_ - length) + " " + num(y) + " l S\n";
            tick_style.h_align = "right";
            tick_style.v_align = "center";
            tick_labels += text_at(format_number(value, axes.tick_digits), tick_style, bx_ - gap - 2.25, y, 0.0, false);
        }
        if (st.tick_color.present && st.tick_width_pt > 0.0) out += "Q\n";
        out += tick_labels;
        TextStyle label_style = st.axis_label;
        label_style.h_align = "center";
        label_style.v_align = "bottom";
        out += text_at(axes.x_label, label_style, bx_ + bw_ / 2.0, 6.0, 0.0, false);
        label_style.v_align = "top";
        out += text_at(axes.y_label, label_style, 6.0, by_ + bh_ / 2.0, 90.0, false);
        if (!axes.title.empty()) {
            TextStyle title_style = st.title;
            title_style.h_align = "center";
            title_style.v_align = "bottom";
            out += text_at(axes.title, title_style, bx_ + bw_ / 2.0, by_ + bh_ + 6.0 + extra_margins_[2], 0.0, false);
        }
        out += legend();
        return out;
    }
};

}  // namespace

std::string scene_to_pdf(const Scene& scene, const PdfOptions& options) {
    Writer writer(scene, options);
    return writer.document();
}

std::pair<double, double> pdf_plot_size_pt(const Scene& scene, const PdfOptions& options) {
    Writer writer(scene, options);
    return writer.plot_size_pt();
}

}  // namespace coolplot
