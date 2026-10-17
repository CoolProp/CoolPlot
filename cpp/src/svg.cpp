#include "coolplot/svg.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <map>

namespace coolplot {

const double PX_PER_PT = 4.0 / 3.0;

// ---------------------------------------------------------------------------
// Ticks (coolplot.render.ticks)
// ---------------------------------------------------------------------------

namespace {

std::vector<double> log_ticks(double lo, double hi, bool minor) {
    int first = static_cast<int>(std::floor(std::log10(lo))), last = static_cast<int>(std::ceil(std::log10(hi)));
    std::vector<double> mantissas;
    if (minor)
        for (int m = 2; m < 10; ++m) mantissas.push_back(m);
    else if (last - first > 2)
        mantissas = {1.0};
    else
        mantissas = {1.0, 2.0, 5.0};
    std::vector<double> found;
    for (int e = first; e <= last; ++e)
        for (double m : mantissas) {
            double t = m * std::pow(10.0, e);
            if (lo <= t && t <= hi) found.push_back(t);
        }
    return found;
}

std::vector<double> linear_ticks(double lo, double hi, bool minor) {
    double span = hi - lo;
    if (!(span > 0.0)) return {lo};
    double raw_step = span / 6.0;
    double magnitude = std::pow(10.0, std::floor(std::log10(raw_step)));
    double step = 10.0 * magnitude;
    for (double m : {1.0, 2.0, 5.0, 10.0})
        if (m * magnitude >= raw_step) {
            step = std::min(step, m * magnitude);
        }
    if (minor) step /= 5.0;
    double start = std::ceil(lo / step) * step;
    int count = static_cast<int>((hi - start) / step + 1e-9) + 1;
    std::vector<double> found;
    for (int i = 0; i < count; ++i) found.push_back(start + i * step);
    return found;
}

}  // namespace

std::vector<double> ticks(double lo, double hi, bool log, bool minor) {
    double a = std::min(lo, hi), b = std::max(lo, hi);
    if (log && a > 0.0) {
        std::vector<double> found = log_ticks(a, b, minor);
        if (found.size() >= 2 || minor) return found;
    }
    return linear_ticks(a, b, minor);
}

// ---------------------------------------------------------------------------
// Text helpers
// ---------------------------------------------------------------------------

namespace {

/// Decode one UTF-8 sequence starting at text[i]; returns the code point and advances i.
unsigned long next_code_point(const std::string& text, size_t& i) {
    unsigned char c = static_cast<unsigned char>(text[i]);
    unsigned long cp;
    int extra;
    if (c < 0x80) {
        cp = c;
        extra = 0;
    } else if ((c & 0xE0) == 0xC0) {
        cp = c & 0x1F;
        extra = 1;
    } else if ((c & 0xF0) == 0xE0) {
        cp = c & 0x0F;
        extra = 2;
    } else if ((c & 0xF8) == 0xF0) {
        cp = c & 0x07;
        extra = 3;
    } else {
        ++i;
        return 0xFFFD;
    }
    ++i;
    for (int k = 0; k < extra; ++k) {
        if (i >= text.size()) return 0xFFFD;
        cp = (cp << 6) | (static_cast<unsigned char>(text[i]) & 0x3F);
        ++i;
    }
    return cp;
}

/// Drop the characters XML 1.0 does not allow anywhere.
std::string clean(const std::string& text) {
    std::string out;
    size_t i = 0;
    while (i < text.size()) {
        size_t start = i;
        unsigned long cp = next_code_point(text, i);
        bool control = cp <= 0x08 || cp == 0x0B || cp == 0x0C || (cp >= 0x0E && cp <= 0x1F);
        bool surrogate = cp >= 0xD800 && cp <= 0xDFFF;
        if (control || surrogate || cp == 0xFFFE || cp == 0xFFFF) continue;
        out.append(text, start, i - start);
    }
    return out;
}

std::string escape(const std::string& text) {
    std::string out;
    for (char c : text) {
        if (c == '&')
            out += "&amp;";
        else if (c == '<')
            out += "&lt;";
        else if (c == '>')
            out += "&gt;";
        else
            out += c;
    }
    return out;
}

std::string num(double value) {
    if (!std::isfinite(value)) throw Error("Non-finite value in SVG output.");
    std::string text = fixed_text(value, 3);  // always has a decimal point
    while (!text.empty() && text.back() == '0') text.pop_back();
    if (!text.empty() && text.back() == '.') text.pop_back();
    return (text == "-0" || text.empty()) ? "0" : text;
}

std::string px(double value_pt) {
    return num(value_pt * PX_PER_PT);
}

std::string css_class(const std::string& prefix, const std::string& value) {
    std::string out;
    bool in_run = false;
    for (char c : value) {
        bool ok = std::isalnum(static_cast<unsigned char>(c)) || c == '_' || c == '-';
        if (ok) {
            out += c;
            in_run = false;
        } else if (!in_run) {
            out += '-';
            in_run = true;
        }
    }
    size_t a = out.find_first_not_of('-'), b = out.find_last_not_of('-');
    out = a == std::string::npos ? "" : out.substr(a, b - a + 1);
    return prefix + out;
}

std::string font_family(const std::vector<std::string>& families) {
    std::string out;
    for (size_t i = 0; i < families.size(); ++i) {
        if (i) out += ", ";
        bool spaced = families[i].find(' ') != std::string::npos;
        out += spaced ? "'" + families[i] + "'" : families[i];
    }
    return out;
}

std::string text_attrs(const TextStyle& style) {
    const Font& f = style.font;
    std::string attrs = "font-family=" + xml_attr(font_family(f.family)) + " font-size=\"" + px(f.size_pt) + "\" font-weight=\"" + f.weight
                        + "\" font-style=\"" + f.style + "\" fill=\"" + style.color.text() + "\" fill-opacity=\"" + num(style.alpha) + "\"";
    if (style.halo_color.present && style.halo_width_pt > 0.0)
        attrs += " stroke=\"" + style.halo_color.hex + "\" stroke-width=\"" + px(2.0 * style.halo_width_pt) + "\" stroke-opacity=\""
                 + num(style.alpha) + "\" stroke-linejoin=\"round\" paint-order=\"stroke\"";
    return attrs;
}

std::string stroke_attrs(const Color& color, double width_pt, const std::vector<double>& dash_pt, double alpha, const std::string& cap,
                         const std::string& join) {
    std::string attrs = "fill=\"none\" stroke=\"" + color.text() + "\" stroke-width=\"" + px(width_pt) + "\" stroke-opacity=\"" + num(alpha)
                        + "\" stroke-linecap=\"" + cap + "\" stroke-linejoin=\"" + join + "\"";
    if (!dash_pt.empty()) {
        attrs += " stroke-dasharray=\"";
        for (size_t i = 0; i < dash_pt.size(); ++i) attrs += (i ? "," : "") + px(dash_pt[i]);
        attrs += "\"";
    }
    return attrs;
}

std::string marker_shape(const std::string& shape, double x, double y, double r) {
    std::string X = num(x), Y = num(y);
    if (shape == "o") return "<circle cx=\"" + X + "\" cy=\"" + Y + "\" r=\"" + num(r) + "\"/>";
    if (shape == "s")
        return "<rect x=\"" + num(x - r) + "\" y=\"" + num(y - r) + "\" width=\"" + num(2 * r) + "\" height=\"" + num(2 * r) + "\"/>";
    std::vector<std::pair<double, double>> points;
    if (shape == "^")
        points = {{0, -r}, {r, r}, {-r, r}};
    else if (shape == "v")
        points = {{0, r}, {r, -r}, {-r, -r}};
    else if (shape == "D")
        points = {{0, -r}, {r, 0}, {0, r}, {-r, 0}};
    if (!points.empty()) {
        std::string d;
        for (size_t i = 0; i < points.size(); ++i) d += (i ? "L" : "") + num(x + points[i].first) + "," + num(y + points[i].second);
        return "<path d=\"M" + d + "Z\"/>";
    }
    if (shape == "x")
        return "<path d=\"M" + num(x - r) + "," + num(y - r) + "L" + num(x + r) + "," + num(y + r) + "M" + num(x - r) + "," + num(y + r) + "L"
               + num(x + r) + "," + num(y - r) + "\"/>";
    if (shape == "+")
        return "<path d=\"M" + num(x - r) + "," + Y + "L" + num(x + r) + "," + Y + "M" + X + "," + num(y - r) + "L" + X + "," + num(y + r)
               + "\"/>";
    throw Error("Unknown marker shape '" + shape + "'.");
}

/// Where a value lies on an axis, 0 at lo and 1 at hi; NaN where it cannot be shown.
double fraction(double v, double lo, double hi, bool log) {
    if (!std::isfinite(v)) return std::nan("");
    if (log) return v > 0 ? (std::log10(v) - std::log10(lo)) / (std::log10(hi) - std::log10(lo)) : std::nan("");
    return (v - lo) / (hi - lo);
}

// ---------------------------------------------------------------------------
// The writer
// ---------------------------------------------------------------------------

class Writer
{
   public:
    Writer(const Scene& scene, const SvgOptions& options) : scene_(scene), options_(options) {
        std::string prefix;
        bool in_run = false;
        for (char c : options.id_prefix) {
            bool ok = std::isalnum(static_cast<unsigned char>(c)) || c == '_' || c == '-';
            if (ok) {
                prefix += c;
                in_run = false;
            } else if (!in_run) {
                prefix += '-';
                in_run = true;
            }
        }
        size_t a = prefix.find_first_not_of('-'), b = prefix.find_last_not_of('-');
        prefix = a == std::string::npos ? "" : prefix.substr(a, b - a + 1);
        // An XML id has to start with a letter or underscore
        bool starts_well = !prefix.empty() && (std::isalpha(static_cast<unsigned char>(prefix[0])) || prefix[0] == '_');
        id_prefix_ = starts_well ? prefix : "cp-" + prefix;
        legend_entries_ = scene.legend_entries();
        limits();
        extra_margins_ = unclipped_margins();
        box();
    }

    std::string document() {
        std::vector<std::string> lines;
        const AxesStyle& st = scene_.axes.style;
        std::string clip = id_prefix_ + "-plot-area";
        lines.push_back("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"" + std::to_string(options_.width) + "\" height=\""
                        + std::to_string(options_.height) + "\" viewBox=\"0 0 " + std::to_string(options_.width) + " "
                        + std::to_string(options_.height) + "\" data-x-log=\"" + (scene_.axes.x_log ? "1" : "0") + "\" data-y-log=\""
                        + (scene_.axes.y_log ? "1" : "0") + "\" data-x-limits=\"" + repr_number(x0_) + " " + repr_number(x1_)
                        + "\" data-y-limits=\"" + repr_number(y0_) + " " + repr_number(y1_) + "\">");
        lines.push_back("<rect class=\"cp-figure\" width=\"100%\" height=\"100%\" fill=\"" + st.figure_background.text() + "\"/>");
        lines.push_back("<defs><clipPath id=\"" + clip + "\"><rect x=\"" + num(bx_) + "\" y=\"" + num(by_) + "\" width=\"" + num(bw_)
                        + "\" height=\"" + num(bh_) + "\"/></clipPath></defs>");
        lines.push_back("<rect class=\"cp-background\" x=\"" + num(bx_) + "\" y=\"" + num(by_) + "\" width=\"" + num(bw_) + "\" height=\""
                        + num(bh_) + "\" fill=\"" + st.background.text() + "\"/>");
        grid(lines);
        lines.push_back("<g class=\"cp-items\">");
        for (size_t i : scene_.draw_order()) {
            std::string element = item_element(scene_.items[i]);
            if (!element.empty()) lines.push_back(element);
        }
        lines.push_back("</g>");
        lines.push_back("<rect class=\"cp-frame\" x=\"" + num(bx_) + "\" y=\"" + num(by_) + "\" width=\"" + num(bw_) + "\" height=\"" + num(bh_)
                        + "\" fill=\"none\" stroke=\"" + st.frame_color.text() + "\" stroke-width=\"" + px(st.frame_width_pt) + "\"/>");
        ticks_and_labels(lines);
        legend(lines);
        lines.push_back("</svg>");
        std::string out;
        for (size_t i = 0; i < lines.size(); ++i) out += (i ? "\n" : "") + lines[i];
        return ascii_only(out);
    }

    std::pair<double, double> plot_size_pt() const {
        return {bw_ / PX_PER_PT, bh_ / PX_PER_PT};
    }

   private:
    const Scene& scene_;
    SvgOptions options_;
    std::string id_prefix_;
    std::vector<std::pair<std::string, std::vector<size_t>>> legend_entries_;
    double x0_ = 0.0, x1_ = 1.0, y0_ = 0.0, y1_ = 1.0;
    std::array<double, 4> extra_margins_ = {0.0, 0.0, 0.0, 0.0};
    double bx_ = 0.0, by_ = 0.0, bw_ = 1.0, bh_ = 1.0;

    bool legend_shown() const {
        return scene_.axes.style.legend.visible && !legend_entries_.empty();
    }

    int legend_chars() const {
        double size_px = scene_.axes.style.legend.text.font.size_pt * PX_PER_PT;
        return std::max(4, static_cast<int>((0.4 * options_.width - 44.0) / (0.6 * size_px)));
    }

    std::string legend_text(const std::string& text) const {
        size_t limit = static_cast<size_t>(legend_chars());
        return text_length(text) <= limit ? text : text_prefix(text, limit - 3) + "...";
    }

    std::pair<double, double> legend_size() const {
        if (!legend_shown()) return {0.0, 0.0};
        double size_px = scene_.axes.style.legend.text.font.size_pt * PX_PER_PT;
        size_t longest = 0;
        for (const auto& entry : legend_entries_) longest = std::max(longest, text_length(legend_text(entry.first)));
        return {44.0 + 0.6 * size_px * longest, 8.0 + 1.6 * size_px * legend_entries_.size()};
    }

    /// The span of the visible lines and markers on one axis (autoscale), or a default.
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

    void limits() {
        const AxesSpec& axes = scene_.axes;
        Range x = axes.has_x_limits ? axes.x_limits : data_limits(true, axes.x_log);
        Range y = axes.has_y_limits ? axes.y_limits : data_limits(false, axes.y_log);
        x = drawable_limits(x, axes.x_log);
        y = drawable_limits(y, axes.y_log);
        x0_ = x.lo;
        x1_ = x.hi;
        y0_ = y.lo;
        y1_ = y.hi;
    }

    /// (left, right, down, up) reach of a text from its anchor in px, from its length and alignment.
    static void text_extent_px(const Item& item, double& left, double& right, double& down, double& up) {
        double size_px = item.text_style.font.size_pt * PX_PER_PT;
        double length = 0.6 * size_px * text_length(item.text), height = 1.25 * size_px;
        bool vertical = item.has_direction && std::fabs(item.direction_y) > std::fabs(item.direction_x);
        double along0, along1, across0, across1;
        const std::string& h = item.text_style.h_align;
        const std::string& v = item.text_style.v_align;
        along0 = h == "left" ? 0.0 : h == "center" ? length / 2 : length;
        along1 = h == "left" ? length : h == "center" ? length / 2 : 0.0;
        across0 = v == "bottom" ? 0.0 : v == "center" ? height / 2 : height;
        across1 = v == "bottom" ? height : v == "center" ? height / 2 : 0.0;
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

    /// Extra (left, right, top, bottom) margins in px for text outside the frame.
    std::array<double, 4> unclipped_margins_array() const {
        std::array<double, 4> need = {0.0, 0.0, 0.0, 0.0};
        for (const Item& item : scene_.items) {
            if (!(item.type == ItemType::Text && item.visible && !item.clip)) continue;
            double fx = fraction(item.text_x, x0_, x1_, scene_.axes.x_log), fy = fraction(item.text_y, y0_, y1_, scene_.axes.y_log);
            if (!(std::isfinite(fx) && std::isfinite(fy))) continue;
            double left, right, down, up;
            text_extent_px(item, left, right, down, up);
            double dx = item.offset_x_pt * PX_PER_PT, dy = item.offset_y_pt * PX_PER_PT;
            double reach[4] = {left - dx + 4.0, right + dx + 4.0, up + dy + 4.0, down - dy + 4.0};
            bool touches[4] = {fx <= 1e-9, fx >= 1.0 - 1e-9, fy >= 1.0 - 1e-9, fy <= 1e-9};
            for (int k = 0; k < 4; ++k) need[k] = std::max(need[k], touches[k] ? reach[k] : 0.0);
        }
        return need;
    }

    std::array<double, 4> unclipped_margins() const {
        std::array<double, 4> need = unclipped_margins_array();
        std::array<double, 4> out;
        for (int k = 0; k < 4; ++k) out[k] = std::max(0.0, need[k] - options_.margins[k]);
        return out;
    }

    void box() {
        double left = options_.margins[0] + extra_margins_[0], right = options_.margins[1] + extra_margins_[1];
        double top = options_.margins[2] + extra_margins_[2], bottom = options_.margins[3] + extra_margins_[3];
        if (scene_.axes.style.legend.location == "outside right") {
            double width = legend_size().first;
            if (width) right += width + 12.0;
        }
        // Never let margins and an outside legend eat the whole drawing
        bw_ = std::max(options_.width - left - right, 0.25 * options_.width);
        bh_ = std::max(options_.height - top - bottom, 0.25 * options_.height);
        bx_ = left;
        by_ = top;
    }

    double to_px_x(double x) const {
        return bx_ + fraction(x, x0_, x1_, scene_.axes.x_log) * bw_;
    }
    double to_px_y(double y) const {
        return by_ + bh_ - fraction(y, y0_, y1_, scene_.axes.y_log) * bh_;
    }

    std::string open(const Item& item, const std::string& extra = "") const {
        std::string classes = "cp-item";
        if (!item.role.empty()) classes += " " + css_class("cp-role-", item.role);
        if (!item.group.empty()) classes += " " + css_class("cp-group-", item.group);
        std::string more = extra;
        bool clips = item.type == ItemType::Text ? item.clip : true;
        if (clips) more = " clip-path=\"url(#" + id_prefix_ + "-plot-area)\"" + more;
        return "<g data-item=" + xml_attr(item.id) + " class=\"" + classes + "\"" + more + ">";
    }

    std::string item_element(const Item& item) const {
        if (!item.visible) return "";
        if (item.type == ItemType::Line) return line(item);
        if (item.type == ItemType::Markers) return markers(item);
        return text(item);
    }

    std::string path_data(const Item& item) const {
        std::string d;
        bool pen_down = false;
        for (size_t i = 0; i < item.x.size(); ++i) {
            double x = to_px_x(item.x[i]), y = to_px_y(item.y[i]);
            if (!(std::isfinite(x) && std::isfinite(y))) {
                pen_down = false;  // NaN, or a non-positive value on a log axis, splits the line
                continue;
            }
            d += (pen_down ? "L" : "M") + num(x) + "," + num(y);
            pen_down = true;
        }
        return d;
    }

    std::string line(const Item& item) const {
        const LineStyle& s = item.line_style;
        std::string d = path_data(item);
        std::vector<double> dash = dash_pattern_pt(s.dash, s.width_pt);
        std::string out = open(item);
        if (s.casing_color.present && s.casing_width_pt > 0.0)
            out += "<path class=\"cp-casing\" d=\"" + d + "\" "
                   + stroke_attrs(s.casing_color, s.width_pt + 2.0 * s.casing_width_pt, dash, s.alpha, s.cap, s.join) + "/>";
        out += "<path class=\"cp-stroke\" d=\"" + d + "\" " + stroke_attrs(s.color, s.width_pt, dash, s.alpha, s.cap, s.join) + "/>";
        return out + "</g>";
    }

    std::string markers(const Item& item) const {
        const MarkerStyle& s = item.marker_style;
        double r = s.size_pt * PX_PER_PT / 2.0;
        std::string face = (s.shape == "x" || s.shape == "+" || !s.face_color.present) ? "none" : s.face_color.hex;
        std::string shapes;
        for (size_t i = 0; i < item.x.size(); ++i) {
            double x = to_px_x(item.x[i]), y = to_px_y(item.y[i]);
            if (std::isfinite(x) && std::isfinite(y)) shapes += marker_shape(s.shape, x, y, r);
        }
        std::string extra = " fill=\"" + face + "\" stroke=\"" + s.edge_color.text() + "\" stroke-width=\"" + px(s.edge_width_pt) + "\" opacity=\""
                            + num(s.alpha) + "\" data-shape=" + xml_attr(s.shape) + " data-size-pt=\"" + num(s.size_pt) + "\"";
        return open(item, extra) + shapes + "</g>";
    }

    double svg_angle(const Item& item, double pxv, double pyv) const {
        if (!item.has_direction) return 0.0;
        double step = 1e-3;
        double qx = to_px_x(item.text_x + item.direction_x * step), qy = to_px_y(item.text_y + item.direction_y * step);
        if (!(std::isfinite(qx) && std::isfinite(qy)) || (qx == pxv && qy == pyv)) return 0.0;
        double angle = std::atan2(qy - pyv, qx - pxv) * 180.0 / 3.14159265358979323846;
        if (angle >= 90.0) return angle - 180.0;
        if (angle < -90.0) return angle + 180.0;
        return angle;
    }

    std::string text(const Item& item) const {
        if (!(std::isfinite(item.text_x) && std::isfinite(item.text_y))) return "";
        double pxv = to_px_x(item.text_x), pyv = to_px_y(item.text_y);
        if (!(std::isfinite(pxv) && std::isfinite(pyv))) return "";
        double offset_x = item.offset_x_pt * PX_PER_PT, offset_y = -item.offset_y_pt * PX_PER_PT;
        double angle = svg_angle(item, pxv, pyv);
        const TextStyle& s = item.text_style;
        std::string anchor = s.h_align == "left" ? "start" : s.h_align == "center" ? "middle" : "end";
        std::string baseline = s.v_align == "bottom" ? "text-after-edge" : s.v_align == "center" ? "central" : "text-before-edge";
        std::string X = num(pxv + offset_x), Y = num(pyv + offset_y);
        return open(item) + "<text x=\"" + X + "\" y=\"" + Y + "\" text-anchor=\"" + anchor + "\" dominant-baseline=\"" + baseline
               + "\" transform=\"rotate(" + num(angle) + " " + X + " " + Y + ")\" " + text_attrs(s) + ">" + xml_text(item.text) + "</text></g>";
    }

    void grid(std::vector<std::string>& lines) const {
        const AxesStyle& st = scene_.axes.style;
        for (int level = 0; level < 2; ++level) {
            bool minor = level == 0;
            if (minor ? !st.has_grid_minor : !st.has_grid_major) continue;
            const LineStyle& g = minor ? st.grid_minor : st.grid_major;
            std::string attrs = stroke_attrs(g.color, g.width_pt, dash_pattern_pt(g.dash, g.width_pt), g.alpha, g.cap, g.join);
            std::string name = minor ? "minor" : "major";
            for (double value : ticks(x0_, x1_, scene_.axes.x_log, minor)) {
                std::string p = num(to_px_x(value));
                lines.push_back("<line class=\"cp-grid-" + name + "\" x1=\"" + p + "\" y1=\"" + num(by_) + "\" x2=\"" + p + "\" y2=\"" + num(by_ + bh_)
                                + "\" " + attrs + "/>");
            }
            for (double value : ticks(y0_, y1_, scene_.axes.y_log, minor)) {
                std::string p = num(to_px_y(value));
                lines.push_back("<line class=\"cp-grid-" + name + "\" x1=\"" + num(bx_) + "\" y1=\"" + p + "\" x2=\"" + num(bx_ + bw_) + "\" y2=\"" + p
                                + "\" " + attrs + "/>");
            }
        }
    }

    void ticks_and_labels(std::vector<std::string>& lines) const {
        const AxesSpec& axes = scene_.axes;
        const AxesStyle& st = axes.style;
        double length = st.tick_length_pt * PX_PER_PT * (st.tick_direction == "out" ? 1.0 : -1.0);
        std::string tick = "stroke=\"" + st.tick_color.text() + "\" stroke-width=\"" + px(st.tick_width_pt) + "\"";
        std::string label_attrs = text_attrs(st.tick_label);
        double gap = st.tick_direction == "out" ? std::fabs(length) : 0.0;
        for (double value : ticks(x0_, x1_, axes.x_log)) {
            std::string p = num(to_px_x(value));
            lines.push_back("<line class=\"cp-tick cp-tick-x\" x1=\"" + p + "\" y1=\"" + num(by_ + bh_) + "\" x2=\"" + p + "\" y2=\""
                            + num(by_ + bh_ + length) + "\" " + tick + "/>");
            lines.push_back("<text class=\"cp-tick-label cp-tick-label-x\" x=\"" + p + "\" y=\"" + num(by_ + bh_ + gap + 3.0)
                            + "\" text-anchor=\"middle\" dominant-baseline=\"text-before-edge\" data-value=\"" + repr_number(value) + "\" "
                            + label_attrs + ">" + format_number(value, axes.tick_digits) + "</text>");
        }
        for (double value : ticks(y0_, y1_, axes.y_log)) {
            std::string p = num(to_px_y(value));
            lines.push_back("<line class=\"cp-tick cp-tick-y\" x1=\"" + num(bx_) + "\" y1=\"" + p + "\" x2=\"" + num(bx_ - length) + "\" y2=\"" + p
                            + "\" " + tick + "/>");
            lines.push_back("<text class=\"cp-tick-label cp-tick-label-y\" x=\"" + num(bx_ - gap - 3.0) + "\" y=\"" + p
                            + "\" text-anchor=\"end\" dominant-baseline=\"central\" data-value=\"" + repr_number(value) + "\" " + label_attrs + ">"
                            + format_number(value, axes.tick_digits) + "</text>");
        }
        lines.push_back("<text class=\"cp-x-label\" x=\"" + num(bx_ + bw_ / 2.0) + "\" y=\"" + num(options_.height - 8.0)
                        + "\" text-anchor=\"middle\" dominant-baseline=\"text-after-edge\" " + text_attrs(st.axis_label) + ">" + xml_text(axes.x_label)
                        + "</text>");
        std::string ymid = num(by_ + bh_ / 2.0);
        lines.push_back("<text class=\"cp-y-label\" x=\"18\" y=\"" + ymid + "\" text-anchor=\"middle\" dominant-baseline=\"central\" transform=\"rotate(-90 18 "
                        + ymid + ")\" " + text_attrs(st.axis_label) + ">" + xml_text(axes.y_label) + "</text>");
        if (!axes.title.empty())
            lines.push_back("<text class=\"cp-title\" x=\"" + num(bx_ + bw_ / 2.0) + "\" y=\"" + num(by_ - 8.0 - extra_margins_[2])
                            + "\" text-anchor=\"middle\" dominant-baseline=\"text-after-edge\" " + text_attrs(st.title) + ">" + xml_text(axes.title)
                            + "</text>");
    }

    void legend_sample(const Item& item, double x, double cy, std::vector<std::string>& out) const {
        if (item.type == ItemType::Line) {
            const LineStyle& s = item.line_style;
            std::vector<double> dash = dash_pattern_pt(s.dash, s.width_pt);
            if (s.casing_color.present && s.casing_width_pt > 0.0)
                out.push_back("<line class=\"cp-casing\" x1=\"" + num(x + 6.0) + "\" y1=\"" + num(cy) + "\" x2=\"" + num(x + 28.0) + "\" y2=\"" + num(cy)
                              + "\" " + stroke_attrs(s.casing_color, s.width_pt + 2.0 * s.casing_width_pt, dash, s.alpha, s.cap, s.join) + "/>");
            out.push_back("<line x1=\"" + num(x + 6.0) + "\" y1=\"" + num(cy) + "\" x2=\"" + num(x + 28.0) + "\" y2=\"" + num(cy) + "\" "
                          + stroke_attrs(s.color, s.width_pt, dash, s.alpha, s.cap, s.join) + "/>");
        } else if (item.type == ItemType::Markers) {
            const MarkerStyle& s = item.marker_style;
            std::string face = (s.shape == "x" || s.shape == "+" || !s.face_color.present) ? "none" : s.face_color.hex;
            out.push_back("<g class=\"cp-legend-marker\" fill=\"" + face + "\" stroke=\"" + s.edge_color.text() + "\" stroke-width=\"" + px(s.edge_width_pt)
                          + "\" opacity=\"" + num(s.alpha) + "\">" + marker_shape(s.shape, x + 17.0, cy, s.size_pt * PX_PER_PT / 2.0) + "</g>");
        }
    }

    void legend(std::vector<std::string>& lines) const {
        const LegendStyle& st = scene_.axes.style.legend;
        std::pair<double, double> size = legend_size();
        if (!size.first) return;
        double pad = 8.0;
        double x = st.location == "upper left" || st.location == "lower left" ? bx_ + pad
                   : st.location == "outside right"                            ? bx_ + bw_ + 12.0
                                                                                : bx_ + bw_ - pad - size.first;
        bool upper = st.location == "upper left" || st.location == "upper right" || st.location == "outside right";
        double y = upper ? by_ + pad : by_ + bh_ - pad - size.second;
        double size_px = st.text.font.size_pt * PX_PER_PT;
        lines.push_back("<g class=\"cp-legend\">");
        lines.push_back("<rect class=\"cp-legend-box\" x=\"" + num(x) + "\" y=\"" + num(y) + "\" width=\"" + num(size.first) + "\" height=\"" + num(size.second)
                        + "\" fill=\"" + st.background.text() + "\" stroke=\"" + st.frame_color.text() + "\"/>");
        for (size_t i = 0; i < legend_entries_.size(); ++i) {
            double cy = y + 4.0 + size_px * (1.6 * i + 0.8);
            lines.push_back("<g class=\"cp-legend-entry\">");
            for (size_t index : legend_entries_[i].second) legend_sample(scene_.items[index], x, cy, lines);
            lines.push_back("<text class=\"cp-legend-text\" x=\"" + num(x + 34.0) + "\" y=\"" + num(cy) + "\" dominant-baseline=\"central\" " + text_attrs(st.text)
                            + ">" + xml_text(legend_text(legend_entries_[i].first)) + "</text></g>");
        }
        lines.push_back("</g>");
    }
};

}  // namespace

std::string xml_text(const std::string& text) {
    return escape(clean(text));
}

std::string xml_attr(const std::string& text) {
    std::string data = escape(clean(text));
    std::string out;
    for (char c : data) {
        if (c == '\n')
            out += "&#10;";
        else if (c == '\r')
            out += "&#13;";
        else if (c == '\t')
            out += "&#9;";
        else
            out += c;
    }
    bool has_double = out.find('"') != std::string::npos, has_single = out.find('\'') != std::string::npos;
    if (has_double) {
        if (has_single) {
            std::string replaced;
            for (char c : out) replaced += c == '"' ? std::string("&quot;") : std::string(1, c);
            return "\"" + replaced + "\"";
        }
        return "'" + out + "'";
    }
    return "\"" + out + "\"";
}

std::string ascii_only(const std::string& text) {
    std::string out;
    size_t i = 0;
    while (i < text.size()) {
        unsigned char c = static_cast<unsigned char>(text[i]);
        if (c < 0x80) {
            out += static_cast<char>(c);
            ++i;
            continue;
        }
        unsigned long cp = next_code_point(text, i);
        out += "&#" + std::to_string(cp) + ";";
    }
    return out;
}

std::string scene_to_svg(const Scene& scene, const SvgOptions& options) {
    Writer writer(scene, options);
    return writer.document();
}

std::pair<double, double> svg_plot_size_pt(const Scene& scene, const SvgOptions& options) {
    Writer writer(scene, options);
    return writer.plot_size_pt();
}

}  // namespace coolplot
