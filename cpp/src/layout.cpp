#include "coolplot/layout.h"

#include <algorithm>
#include <cmath>

namespace coolplot {

const double LABEL_CHAR_WIDTH = 0.55;
const double LABEL_LINE_HEIGHT = 1.25;
const double LABEL_PAD_PT = 2.0;
const double LABEL_MAX_BEND_DEG = 35.0;

namespace {

const std::vector<std::string> EDGES = {"top", "right", "bottom", "left"};
const double PI = 3.14159265358979323846;
const double NaN = std::nan("");

double axis_to_pt(double value, Range limits, bool log, double size) {
    double lo = limits.lo, hi = limits.hi;
    if (log) {
        value = value > 0.0 ? std::log10(value) : NaN;
        lo = std::log10(lo);
        hi = std::log10(hi);
    }
    return (value - lo) / (hi - lo) * size;
}

double pt_to_axis(double value, Range limits, bool log, double size) {
    double lo = limits.lo, hi = limits.hi;
    if (log) {
        lo = std::log10(lo);
        hi = std::log10(hi);
    }
    double out = lo + value / size * (hi - lo);
    return log ? std::pow(10.0, out) : out;
}

double interp(double s, const std::vector<double>& xs, const std::vector<double>& ys) {
    // numpy.interp: clamped at the ends, linear in between
    if (s <= xs.front()) return ys.front();
    if (s >= xs.back()) return ys.back();
    size_t i = static_cast<size_t>(std::upper_bound(xs.begin(), xs.end(), s) - xs.begin());
    // numpy's formula, so that both give the same bits
    double slope = (ys[i] - ys[i - 1]) / (xs[i] - xs[i - 1]);
    return slope * (s - xs[i - 1]) + ys[i - 1];
}

}  // namespace

double Frame::x_to_pt(double x) const {
    return axis_to_pt(x, x_limits, x_log, width_pt);
}
double Frame::y_to_pt(double y) const {
    return axis_to_pt(y, y_limits, y_log, height_pt);
}
double Frame::x_to_data(double px) const {
    return pt_to_axis(px, x_limits, x_log, width_pt);
}
double Frame::y_to_data(double py) const {
    return pt_to_axis(py, y_limits, y_log, height_pt);
}

bool Frame::usable() const {
    bool ok = x_limits.hi > x_limits.lo && y_limits.hi > y_limits.lo && width_pt > 0.0 && height_pt > 0.0;
    if (x_log) ok = ok && x_limits.lo > 0.0;
    if (y_log) ok = ok && y_limits.lo > 0.0;
    return ok;
}

std::pair<double, double> text_size_pt(const std::string& text, const TextStyle& style) {
    double size = style.font.size_pt;
    return {LABEL_CHAR_WIDTH * size * std::max<size_t>(text_length(text), 1), LABEL_LINE_HEIGHT * size};
}

// ---------------------------------------------------------------------------
// Rotated boxes
// ---------------------------------------------------------------------------

namespace {

struct Box
{
    double cx, cy, angle, half_w, half_h;

    void axes(double& ux, double& uy, double& vx, double& vy) const {
        double c = std::cos(angle), s = std::sin(angle);
        ux = c;
        uy = s;
        vx = -s;
        vy = c;
    }
    std::vector<std::pair<double, double>> corners() const {
        double ux, uy, vx, vy;
        axes(ux, uy, vx, vy);
        std::vector<std::pair<double, double>> out;
        for (auto ab : {std::make_pair(-1, -1), std::make_pair(1, -1), std::make_pair(1, 1), std::make_pair(-1, 1)})
            out.push_back({cx + ab.first * half_w * ux + ab.second * half_h * vx, cy + ab.first * half_w * uy + ab.second * half_h * vy});
        return out;
    }
    bool inside(double width, double height, double inset) const {
        for (auto& c : corners())
            if (!(inset <= c.first && c.first <= width - inset && inset <= c.second && c.second <= height - inset)) return false;
        return true;
    }
    bool near_points(const std::vector<double>& px, const std::vector<double>& py, double margin) const {
        double ux, uy, vx, vy;
        axes(ux, uy, vx, vy);
        for (size_t i = 0; i < px.size(); ++i) {
            double dx = px[i] - cx, dy = py[i] - cy;
            double u = std::fabs(dx * ux + dy * uy), v = std::fabs(dx * vx + dy * vy);
            if (u <= half_w + margin && v <= half_h + margin) return true;
        }
        return false;
    }
    /// Separating axis test for two rotated rectangles, with padding.
    bool overlaps(const Box& other, double pad) const {
        std::vector<std::pair<double, double>> a = corners(), b = other.corners();
        for (const Box* box : {this, &other}) {
            double ux, uy, vx, vy;
            box->axes(ux, uy, vx, vy);
            for (auto axis : {std::make_pair(ux, uy), std::make_pair(vx, vy)}) {
                double min_a = 1e300, max_a = -1e300, min_b = 1e300, max_b = -1e300;
                for (auto& c : a) {
                    double p = c.first * axis.first + c.second * axis.second;
                    min_a = std::min(min_a, p);
                    max_a = std::max(max_a, p);
                }
                for (auto& c : b) {
                    double p = c.first * axis.first + c.second * axis.second;
                    min_b = std::min(min_b, p);
                    max_b = std::max(max_b, p);
                }
                if (max_a + pad < min_b || max_b + pad < min_a) return false;
            }
        }
        return true;
    }
};

}  // namespace

// ---------------------------------------------------------------------------
// Lines in plot coordinates
// ---------------------------------------------------------------------------

std::pair<double, double> Piece::at(double s) const {
    return {interp(s, arc, px), interp(s, arc, py)};
}

std::pair<double, double> Piece::project(double qx, double qy) const {
    double best_dist = 1e300, best_s = 0.0;
    for (size_t i = 0; i + 1 < px.size(); ++i) {
        double ax = px[i], ay = py[i], dx = px[i + 1] - ax, dy = py[i + 1] - ay;
        double seg = dx * dx + dy * dy;
        double t = is_zero(seg) ? 0.0 : std::min(std::max(((qx - ax) * dx + (qy - ay) * dy) / seg, 0.0), 1.0);
        double dist = std::hypot(ax + t * dx - qx, ay + t * dy - qy);
        if (dist < best_dist) {  // the first of equally near segments
            best_dist = dist;
            best_s = arc[i] + t * std::sqrt(seg);
        }
    }
    return {best_s, best_dist};
}

namespace {

Piece make_piece(std::vector<double> xs, std::vector<double> ys, const std::string& start_edge, const std::string& end_edge) {
    Piece piece;
    piece.px = std::move(xs);
    piece.py = std::move(ys);
    piece.start_edge = start_edge;
    piece.end_edge = end_edge;
    piece.arc.push_back(0.0);
    for (size_t i = 1; i < piece.px.size(); ++i)
        piece.arc.push_back(piece.arc.back() + std::hypot(piece.px[i] - piece.px[i - 1], piece.py[i] - piece.py[i - 1]));
    return piece;
}

const char* EDGE_NAMES_BY_CODE[] = {"left", "right", "bottom", "top"};

/// The code of the frame edge a point lies on, or -1; later edges win, so top comes first.
int on_edges(double x, double y, double width, double height) {
    double near = 1e-6 * std::max(width, height);
    int code = -1;
    if (std::fabs(x - 0.0) <= near) code = 0;
    if (std::fabs(y - 0.0) <= near) code = 2;
    if (std::fabs(x - width) <= near) code = 1;
    if (std::fabs(y - height) <= near) code = 3;
    return code;
}

struct Clipped
{
    double t0, t1;
    int edge0, edge1;
    bool visible;
};

/// Liang-Barsky clipping of one segment to the plot area.
Clipped clip_segment(double x0, double y0, double x1, double y1, double width, double height) {
    Clipped c = {0.0, 1.0, -1, -1, std::isfinite(x0) && std::isfinite(y0) && std::isfinite(x1) && std::isfinite(y1)};
    double dx = x1 - x0, dy = y1 - y0;
    double p[4] = {-dx, dx, -dy, dy};
    double q[4] = {x0, width - x0, y0, height - y0};
    for (int code = 0; code < 4; ++code) {
        bool parallel = is_zero(p[code]);
        if (parallel && q[code] < 0.0) c.visible = false;
        double t = q[code] / (parallel ? 1.0 : p[code]);
        if (p[code] < 0.0 && t > c.t0) {
            c.t0 = t;
            c.edge0 = code;
        }
        if (p[code] > 0.0 && t < c.t1) {
            c.t1 = t;
            c.edge1 = code;
        }
    }
    if (!(c.t0 <= c.t1)) c.visible = false;
    if (c.edge0 == -1) c.edge0 = on_edges(x0, y0, width, height);
    if (c.edge1 == -1) c.edge1 = on_edges(x1, y1, width, height);
    return c;
}

}  // namespace

std::vector<Piece> visible_pieces(const std::vector<double>& px, const std::vector<double>& py, double width, double height) {
    std::vector<Piece> pieces;
    if (px.size() < 2) return pieces;
    size_t n = px.size() - 1;
    std::vector<Clipped> segments;
    for (size_t i = 0; i < n; ++i) segments.push_back(clip_segment(px[i], py[i], px[i + 1], py[i + 1], width, height));
    // A piece starts at a visible segment that enters through an edge or
    // follows an invisible segment or one that left through an edge; it
    // ends at a segment that leaves, or is followed by one that does not
    // continue it.
    std::vector<size_t> starts, ends;
    for (size_t i = 0; i < n; ++i) {
        if (!segments[i].visible) continue;
        bool before = i > 0 && segments[i - 1].visible;
        bool left_before = i == 0 || segments[i - 1].edge1 != -1;
        if (segments[i].edge0 != -1 || !before || left_before) starts.push_back(i);
        bool after = i + 1 < n && segments[i + 1].visible;
        bool enters_after = i + 1 >= n || segments[i + 1].edge0 != -1;
        if (segments[i].edge1 != -1 || !after || enters_after) ends.push_back(i);
    }
    for (size_t k = 0; k < starts.size() && k < ends.size(); ++k) {
        size_t a = starts[k], b = ends[k];
        std::vector<double> xs, ys;
        xs.push_back(px[a] + segments[a].t0 * (px[a + 1] - px[a]));
        ys.push_back(py[a] + segments[a].t0 * (py[a + 1] - py[a]));
        for (size_t i = a; i <= b; ++i) {
            xs.push_back(px[i] + segments[i].t1 * (px[i + 1] - px[i]));
            ys.push_back(py[i] + segments[i].t1 * (py[i + 1] - py[i]));
        }
        std::string start_edge = segments[a].edge0 != -1 ? EDGE_NAMES_BY_CODE[segments[a].edge0] : "";
        std::string end_edge = segments[b].edge1 != -1 ? EDGE_NAMES_BY_CODE[segments[b].edge1] : "";
        pieces.push_back(make_piece(xs, ys, start_edge, end_edge));
    }
    return pieces;
}

// ---------------------------------------------------------------------------
// Edge labels
// ---------------------------------------------------------------------------

namespace {

struct Candidate
{
    double score;
    Box box;
    double dir_x, dir_y;  // along the line at the label, in pt
};

/// A label centred at arc length s, aligned with the chord over its length; false if none.
bool candidate(const Piece& piece, double s, double half_w, double half_h, double score, Candidate& out) {
    if (s - half_w < 0.0 || s + half_w > piece.length()) return false;
    std::pair<double, double> a = piece.at(s - half_w), m = piece.at(s), b = piece.at(s + half_w);
    double dx = b.first - a.first, dy = b.second - a.second;
    if (is_zero(dx) && is_zero(dy)) return false;
    double first = std::atan2(m.second - a.second, m.first - a.first), second = std::atan2(b.second - m.second, b.first - m.first);
    double turn = second - first + PI;
    turn = std::fmod(turn, 2.0 * PI);  // Python's modulo keeps the sign of the divisor
    if (turn < 0.0) turn += 2.0 * PI;
    turn -= PI;
    double bend = std::fabs(turn * (180.0 / PI));  // math.degrees multiplies by 180/pi, bit for bit
    if (bend > LABEL_MAX_BEND_DEG) return false;
    double angle = std::atan2(dy, dx);
    if (angle > PI / 2.0)
        angle -= PI;
    else if (angle <= -PI / 2.0)
        angle += PI;
    // The bend counts in whole millionths of a degree, so that two spots whose
    // bends differ only by rounding noise tie, and the order they were found
    // in decides, the same way in Python and C++
    double bend_micro = std::floor(bend * 1e6 + 0.5);
    out = {score + bend_micro * 5e-8, Box{m.first, m.second, angle, half_w, half_h}, dx, dy};
    return true;
}

std::vector<Candidate> edge_candidates(const Piece& piece, double half_w, double half_h, const std::vector<std::string>& preferred) {
    std::vector<Candidate> found;
    for (int side = 0; side < 2; ++side) {
        const std::string& edge = side == 0 ? piece.start_edge : piece.end_edge;
        bool forward = side == 0;
        if (edge.empty()) continue;
        auto at = std::find(preferred.begin(), preferred.end(), edge);
        double rank = at != preferred.end() ? static_cast<double>(at - preferred.begin()) : preferred.size() + 1.0;
        for (int k = 0; k < 3; ++k) {  // slide inward if the spot next to the frame is taken
            double s = half_w + LABEL_PAD_PT + half_h + k * 2.0 * half_w;
            Candidate c;
            if (candidate(piece, forward ? s : piece.length() - s, half_w, half_h, rank + 0.5 * k, c)) found.push_back(c);
        }
    }
    return found;
}

std::vector<Candidate> previous_candidates(const std::vector<Piece>& pieces, double half_w, double half_h, double prev_x, double prev_y,
                                           bool fallback) {
    double edge_reach = half_w + LABEL_PAD_PT + half_h + 4.0 * half_w + 1.0;
    std::vector<Candidate> found;
    for (const Piece& piece : pieces) {
        std::pair<double, double> sd = piece.project(prev_x, prev_y);
        bool near_edge = (!piece.start_edge.empty() && sd.first <= edge_reach) || (!piece.end_edge.empty() && piece.length() - sd.first <= edge_reach);
        if (sd.second <= 3.0 && (fallback || near_edge)) {
            Candidate c;
            if (candidate(piece, sd.first, half_w, half_h, -10.0, c)) found.push_back(c);
        }
    }
    return found;
}

std::vector<Candidate> candidates(const std::vector<Piece>& pieces, double half_w, double half_h, const std::vector<std::string>& preferred,
                                  bool has_previous, double prev_x, double prev_y, bool fallback) {
    std::vector<Candidate> found;
    if (has_previous) found = previous_candidates(pieces, half_w, half_h, prev_x, prev_y, fallback);
    for (const Piece& piece : pieces) {
        std::vector<Candidate> edges = edge_candidates(piece, half_w, half_h, preferred);
        found.insert(found.end(), edges.begin(), edges.end());
        if (fallback)
            for (double fraction : {0.5, 0.25, 0.75}) {
                Candidate c;
                if (candidate(piece, fraction * piece.length(), half_w, half_h, EDGES.size() + 2.0, c)) found.push_back(c);
            }
    }
    std::stable_sort(found.begin(), found.end(), [](const Candidate& a, const Candidate& b) { return a.score < b.score; });
    return found;
}

void keep_out_points(const Frame& frame, const std::vector<KeepOut>& lines, std::vector<double>& xs, std::vector<double>& ys,
                     double spacing_pt = 2.0) {
    for (const KeepOut& entry : lines) {
        std::vector<double> px, py;
        for (size_t i = 0; i < entry.x.size(); ++i) {
            px.push_back(frame.x_to_pt(entry.x[i]));
            py.push_back(frame.y_to_pt(entry.y[i]));
        }
        for (size_t i = 0; i < px.size(); ++i) {
            if (!(std::isfinite(px[i]) && std::isfinite(py[i]))) continue;
            xs.push_back(px[i]);
            ys.push_back(py[i]);
            if (entry.joined && i + 1 < px.size() && std::isfinite(px[i + 1]) && std::isfinite(py[i + 1])) {
                double steps = std::floor(std::hypot(px[i + 1] - px[i], py[i + 1] - py[i]) / spacing_pt);
                int n = steps > 1e7 ? 10000000 : static_cast<int>(steps);  // a segment 20 km long on paper is enough
                for (int k = 1; k <= n; ++k) {
                    double t = k / (n + 1.0);
                    xs.push_back(px[i] + t * (px[i + 1] - px[i]));
                    ys.push_back(py[i] + t * (py[i + 1] - py[i]));
                }
            }
        }
    }
}

bool is_free(const Box& box, const Frame& frame, const std::vector<double>& kx, const std::vector<double>& ky, double keep_out_pt,
             const std::vector<Box>& placed) {
    if (!box.inside(frame.width_pt, frame.height_pt, LABEL_PAD_PT)) return false;
    if (box.near_points(kx, ky, keep_out_pt)) return false;
    for (const Box& other : placed)
        if (box.overlaps(other, LABEL_PAD_PT)) return false;
    return true;
}

Item label_item(const LabelRequest& request, double x, double y, bool has_direction, double dx, double dy, const std::string& h_align,
                const std::string& v_align, double offset_x, double offset_y, bool clip) {
    Item t;
    t.type = ItemType::Text;
    t.id = request.id;
    t.group = request.group;
    t.role = "isoline_label";
    t.text_x = x;
    t.text_y = y;
    t.text = request.text;
    t.has_direction = has_direction;
    t.direction_x = dx;
    t.direction_y = dy;
    t.text_style = request.style;
    t.text_style.h_align = h_align;
    t.text_style.v_align = v_align;
    t.offset_x_pt = offset_x;
    t.offset_y_pt = offset_y;
    t.clip = clip;
    t.z_order = 4.0;
    return t;
}

Item edge_text(const LabelRequest& request, const Frame& frame, const Box& box, double dir_x, double dir_y) {
    double x0 = frame.x_to_data(box.cx - 0.5 * dir_x), x1 = frame.x_to_data(box.cx + 0.5 * dir_x);
    double y0 = frame.y_to_data(box.cy - 0.5 * dir_y), y1 = frame.y_to_data(box.cy + 0.5 * dir_y);
    double cx = frame.x_to_data(box.cx), cy = frame.y_to_data(box.cy);
    double dx = x1 - x0, dy = y1 - y0;
    bool has_direction = std::isfinite(dx) && std::isfinite(dy);
    return label_item(request, cx, cy, has_direction, dx, dy, "center", "center", 0.0, 0.0, true);
}

}  // namespace

std::vector<Item> place_edge_labels(const std::vector<LabelRequest>& requests, const Frame& frame, const std::vector<KeepOut>& keep_out,
                                    double keep_out_pt, const std::map<std::string, std::vector<std::string>>& preferred_edges,
                                    const std::map<std::string, Item>& previous, bool fallback) {
    std::vector<Item> labels;
    if (!frame.usable()) return labels;
    std::vector<double> kx, ky;
    keep_out_points(frame, keep_out, kx, ky);
    std::vector<Box> placed;
    for (const LabelRequest& request : requests) {
        std::pair<double, double> size = text_size_pt(request.text, request.style);
        double half_w = 0.5 * size.first, half_h = 0.5 * size.second;
        std::vector<double> px, py;
        for (size_t i = 0; i < request.x.size(); ++i) {
            px.push_back(frame.x_to_pt(request.x[i]));
            py.push_back(frame.y_to_pt(request.y[i]));
        }
        std::vector<Piece> pieces = visible_pieces(px, py, frame.width_pt, frame.height_pt);
        auto old = previous.find(request.id);
        bool has_old = false;
        double old_x = 0.0, old_y = 0.0;
        if (old != previous.end()) {
            old_x = frame.x_to_pt(old->second.text_x);
            old_y = frame.y_to_pt(old->second.text_y);
            has_old = std::isfinite(old_x) && std::isfinite(old_y);
        }
        auto pref = preferred_edges.find(request.family);
        const std::vector<std::string>& preferred = pref != preferred_edges.end() ? pref->second : EDGES;
        for (const Candidate& c : candidates(pieces, half_w, half_h, preferred, has_old, old_x, old_y, fallback)) {
            if (!is_free(c.box, frame, kx, ky, keep_out_pt, placed)) continue;
            placed.push_back(c.box);
            Item fresh = edge_text(request, frame, c.box, c.dir_x, c.dir_y);
            // The old item is kept when the new label is the old one in the same place
            bool same = has_old && old->second.text == fresh.text && old->second.text_style == fresh.text_style
                        && std::hypot(c.box.cx - old_x, c.box.cy - old_y) < 0.5;
            labels.push_back(same ? old->second : fresh);
            break;
        }
    }
    return labels;
}

// ---------------------------------------------------------------------------
// Margin labels
// ---------------------------------------------------------------------------

std::vector<Item> place_margin_labels(const std::vector<LabelRequest>& requests, const Frame& frame, const std::vector<std::string>& edges,
                                      double gap_pt) {
    std::vector<Item> labels;
    if (!frame.usable()) return labels;
    std::map<std::string, std::vector<std::pair<double, double>>> taken;
    for (const std::string& edge : edges) taken[edge];
    for (const LabelRequest& request : requests) {
        std::pair<double, double> size = text_size_pt(request.text, request.style);
        double half = 0.5 * size.second + LABEL_PAD_PT;
        std::vector<double> px, py;
        for (size_t i = 0; i < request.x.size(); ++i) {
            px.push_back(frame.x_to_pt(request.x[i]));
            py.push_back(frame.y_to_pt(request.y[i]));
        }
        for (const Piece& piece : visible_pieces(px, py, frame.width_pt, frame.height_pt)) {
            // Where the piece leaves the frame through a labelled edge
            std::string edge;
            double x = 0.0, y = 0.0;
            if (taken.count(piece.start_edge)) {
                edge = piece.start_edge;
                x = piece.px.front();
                y = piece.py.front();
            } else if (taken.count(piece.end_edge)) {
                edge = piece.end_edge;
                x = piece.px.back();
                y = piece.py.back();
            } else {
                continue;
            }
            bool horizontal_edge = edge == "top" || edge == "bottom";
            double along = horizontal_edge ? x : y;
            double limit = horizontal_edge ? frame.width_pt : frame.height_pt;
            if (along - half < -LABEL_PAD_PT || along + half > limit + LABEL_PAD_PT) continue;
            bool free = true;
            for (auto& ah : taken[edge])
                if (std::fabs(along - ah.first) < half + ah.second) free = false;
            if (!free) continue;
            taken[edge].push_back({along, half});
            // Snap onto the frame exactly, so the text sits at the same distance from it for every line
            std::string h_align, v_align = "center";
            double off_x = 0.0, off_y = 0.0;
            bool vertical = horizontal_edge;
            if (edge == "top") {
                h_align = "left";
                off_y = gap_pt;
                y = frame.height_pt;
            } else if (edge == "bottom") {
                h_align = "right";
                off_y = -gap_pt;
                y = 0.0;
            } else if (edge == "right") {
                h_align = "left";
                off_x = gap_pt;
                x = frame.width_pt;
            } else {
                h_align = "right";
                off_x = -gap_pt;
                x = 0.0;
            }
            labels.push_back(label_item(request, frame.x_to_data(x), frame.y_to_data(y), vertical, 0.0, 1.0, h_align, v_align, off_x, off_y, false));
            break;
        }
    }
    return labels;
}

// ---------------------------------------------------------------------------
// State numbers
// ---------------------------------------------------------------------------

std::vector<Item> place_state_numbers(const std::vector<Item>& numbers, const Frame& frame, const std::vector<double>& marker_x,
                                      const std::vector<double>& marker_y) {
    if (!frame.usable()) return numbers;
    struct Spot
    {
        int sx, sy;
        const char* h_align;
        const char* v_align;
    };
    static const Spot SPOTS[] = {{1, 1, "left", "bottom"}, {-1, 1, "right", "bottom"}, {1, -1, "left", "top"}, {-1, -1, "right", "top"}};
    std::vector<double> mx, my;
    for (size_t i = 0; i < marker_x.size(); ++i) {
        mx.push_back(frame.x_to_pt(marker_x[i]));
        my.push_back(frame.y_to_pt(marker_y[i]));
    }
    std::vector<Box> placed;
    std::vector<Item> out;
    for (const Item& t : numbers) {
        double px = frame.x_to_pt(t.text_x), py = frame.y_to_pt(t.text_y);
        if (!(std::isfinite(px) && std::isfinite(py))) {
            out.push_back(t);
            continue;
        }
        std::pair<double, double> size = text_size_pt(t.text, t.text_style);
        double width = size.first, height = size.second;
        double distance = std::fabs(t.offset_x_pt);
        std::vector<double> ox, oy;  // every marker but its own
        for (size_t i = 0; i < mx.size(); ++i)
            if (std::hypot(mx[i] - px, my[i] - py) > 0.5) {
                ox.push_back(mx[i]);
                oy.push_back(my[i]);
            }
        const Spot* choice = nullptr;
        Box box = {0.0, 0.0, 0.0, 0.5 * width, 0.5 * height};
        for (const Spot& spot : SPOTS) {
            box = Box{px + spot.sx * (distance + 0.5 * width), py + spot.sy * (distance + 0.5 * height), 0.0, 0.5 * width, 0.5 * height};
            bool blocked = box.near_points(ox, oy, 2.0);
            for (const Box& b : placed)
                if (box.overlaps(b, 0.5)) blocked = true;
            if (!blocked) {
                choice = &spot;
                break;
            }
        }
        if (!choice) {
            choice = &SPOTS[0];
            box = Box{px + distance + 0.5 * width, py + distance + 0.5 * height, 0.0, 0.5 * width, 0.5 * height};
        }
        placed.push_back(box);
        Item moved = t;
        moved.offset_x_pt = choice->sx * distance;
        moved.offset_y_pt = choice->sy * distance;
        moved.text_style.h_align = choice->h_align;
        moved.text_style.v_align = choice->v_align;
        out.push_back(moved);
    }
    return out;
}

}  // namespace coolplot
