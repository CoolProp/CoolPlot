/*
 * coolplot scene_svg.js: the SVG document of a CoolPlot scene, in the browser.
 *
 * A port of coolplot.render.svg (and cpp/src/svg.cpp): it takes the scene
 * record of docs/reference/contracts.md (section 3) and returns the same
 * SVG text, byte for byte, so a page can draw a chart from scene JSON
 * without a server. Plain ES2017, no libraries, ASCII only.
 *
 *   var svg = CoolPlotScene.toSvg(scene, {width: 800, height: 600,
 *                                         margins: [80, 20, 40, 60], idPrefix: "coolplot"});
 *
 * Works in a browser (window.CoolPlotScene) and in Node (module.exports).
 */
(function (root) {
  "use strict";

  var PX_PER_PT = 4.0 / 3.0;
  var DASHES = { solid: [], dashed: [3.7, 1.6], dotted: [1.0, 1.65], dashdot: [6.4, 1.6, 1.0, 1.6] };

  // Numbers ---------------------------------------------------------------

  // Rounding as Python and C do it. JavaScript's toFixed and toPrecision
  // round an exact tie (a value exactly halfway, such as 0.0625 to three
  // decimals) away from zero; Python and printf round it to the even digit.
  // Ties are rare (only values with a short binary fraction can be one), so
  // the JavaScript result is kept unless the value is an exact tie whose
  // last kept digit would be even, and then the value one step closer to
  // zero is rounded instead, which gives the even digit.

  // The exact decimal digits of |value| as "int.frac".
  function exactText(abs) {
    if (abs >= 1e21) { return BigInt(abs).toString() + ".0"; }   // such doubles are integers
    return abs.toFixed(100);   // enough digits for every value that can be a tie here
  }

  // Whether rounding |value| to `decimals` digits after the point (negative:
  // before it) is an exact tie that half-to-even rounds towards zero.
  function tieRoundsDown(abs, decimals) {
    var text = exactText(abs), point = text.indexOf(".");
    var digits = text.replace(".", "");
    var first = point + decimals;   // index of the first dropped digit
    if (first <= 0 || first >= digits.length || digits[first] !== "5") { return false; }
    if (!/^0*$/.test(digits.slice(first + 1))) { return false; }
    return Number(digits[first - 1]) % 2 === 0;
  }

  // The neighbouring double closer to zero (value is not zero).
  function towardZero(value) {
    var buffer = new Float64Array([value]);
    var bits = new BigInt64Array(buffer.buffer);
    bits[0] -= BigInt(1);
    return buffer[0];
  }

  // value.toFixed(decimals), rounded half to even and without exponent.
  function toFixedEven(value, decimals) {
    var abs = Math.abs(value);
    if (abs >= 1e21) {
      return (value < 0 ? "-" : "") + BigInt(abs).toString() + (decimals > 0 ? "." + "0".repeat(decimals) : "");
    }
    if (value !== 0 && tieRoundsDown(abs, decimals)) { value = towardZero(value); }
    return value.toFixed(decimals);
  }

  // value.toPrecision(digits), rounded half to even.
  function toPrecisionEven(value, digits) {
    var abs = Math.abs(value);
    var exponent = parseInt(abs.toExponential().split("e")[1], 10);
    if (tieRoundsDown(abs, digits - 1 - exponent)) { value = towardZero(value); }
    return value.toPrecision(digits);
  }

  // "%.3f" with trailing zeros dropped, as the C and Python writers do.
  function num(value) {
    if (!isFinite(value)) { throw new Error("Non-finite value in SVG output."); }
    var text = toFixedEven(value, 3);
    if (text.indexOf(".") >= 0) { text = text.replace(/0+$/, "").replace(/\.$/, ""); }
    return (text === "-0" || text === "") ? "0" : text;
  }

  function px(valuePt) { return num(valuePt * PX_PER_PT); }

  // Python's repr of a float: the shortest text that reads back, ".0" on
  // integers, exponents with at least two digits, below 1e-4 and from 1e16.
  function reprNumber(value) {
    if (isNaN(value)) { return "nan"; }
    if (!isFinite(value)) { return value > 0 ? "inf" : "-inf"; }
    if (value === 0) { return (1 / value < 0) ? "-0.0" : "0.0"; }
    var parts = value.toExponential().split("e");
    var sign = parts[0][0] === "-" ? "-" : "";
    var digits = parts[0].replace("-", "").replace(".", "");
    var exponent = parseInt(parts[1], 10);
    var magnitude = Math.abs(value);
    if (magnitude >= 1e16 || magnitude < 1e-4) {
      var mantissa = digits.length > 1 ? digits[0] + "." + digits.slice(1) : digits;
      return sign + mantissa + "e" + (exponent < 0 ? "-" : "+") + (Math.abs(exponent) < 10 ? "0" : "") + Math.abs(exponent);
    }
    var text;
    if (exponent >= 0) {
      if (digits.length <= exponent + 1) {
        text = digits + "0".repeat(exponent + 1 - digits.length) + ".0";
      } else {
        text = digits.slice(0, exponent + 1) + "." + digits.slice(exponent + 1);
      }
    } else {
      text = "0." + "0".repeat(-exponent - 1) + digits;
    }
    return sign + text;
  }

  function stripZeros(text) {
    if (text.indexOf(".") < 0) { return text; }
    return text.replace(/0+$/, "").replace(/\.$/, "");
  }

  // coolplot.core.numbers.format_number
  function formatNumber(value, digits) {
    if (digits === undefined) { digits = 6; }
    if (isNaN(value)) { return "nan"; }
    if (!isFinite(value)) { return value > 0 ? "inf" : "-inf"; }
    if (value === 0) { return "0"; }
    var rounded = parseFloat(toPrecisionEven(value, digits));
    if (!isFinite(rounded)) { rounded = value; }   // rounding up the largest numbers overflows
    var magnitude = Math.abs(rounded);
    if (magnitude >= 1e-3 && magnitude < 1e6) {
      var exponent = Math.floor(Math.log10(magnitude));
      var decimals = Math.max(0, digits - 1 - exponent);
      var text = stripZeros(rounded.toFixed(decimals));
      return (text === "-0" || text === "") ? "0" : text;
    }
    var parts = rounded.toExponential(digits - 1).split("e");
    return stripZeros(parts[0]) + "e" + parseInt(parts[1], 10);
  }

  // Ticks (coolplot.render.ticks) ----------------------------------------

  function logTicks(lo, hi, minor) {
    var first = Math.floor(Math.log10(lo)), last = Math.ceil(Math.log10(hi));
    var mantissas = minor ? [2, 3, 4, 5, 6, 7, 8, 9] : (last - first > 2 ? [1] : [1, 2, 5]);
    var found = [];
    for (var e = first; e <= last; e++) {
      for (var i = 0; i < mantissas.length; i++) {
        var t = mantissas[i] * Number("1e" + e);   // exact, as 10.0 ** e in Python
        if (lo <= t && t <= hi) { found.push(t); }
      }
    }
    return found;
  }

  function linearTicks(lo, hi, minor) {
    var span = hi - lo;
    if (!(span > 0)) { return [lo]; }
    var raw = span / 6.0;
    var magnitude = Number("1e" + Math.floor(Math.log10(raw)));
    var step = 10 * magnitude;
    [1, 2, 5, 10].forEach(function (m) { if (m * magnitude >= raw) { step = Math.min(step, m * magnitude); } });
    if (minor) { step /= 5.0; }
    var start = Math.ceil(lo / step) * step;
    var count = Math.floor((hi - start) / step + 1e-9) + 1;
    var found = [];
    for (var i = 0; i < count; i++) { found.push(start + i * step); }
    return found;
  }

  function ticks(lo, hi, log, minor) {
    var a = Math.min(lo, hi), b = Math.max(lo, hi);
    if (log && a > 0) {
      var found = logTicks(a, b, minor);
      if (found.length >= 2 || minor) { return found; }
    }
    return linearTicks(a, b, minor);
  }

  // Text --------------------------------------------------------------------

  // Characters XML 1.0 does not allow anywhere are dropped.
  function clean(text) {
    return String(text).replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]/g, "")
      .replace(/[\ud800-\udbff](?![\udc00-\udfff])|(^|[^\ud800-\udbff])[\udc00-\udfff]/g, "$1");
  }

  function escape(text) {
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function xmlText(text) { return escape(clean(text)); }

  // xml.sax.saxutils.quoteattr
  function xmlAttr(text) {
    var data = escape(clean(text)).replace(/\n/g, "&#10;").replace(/\r/g, "&#13;").replace(/\t/g, "&#9;");
    if (data.indexOf('"') >= 0) {
      if (data.indexOf("'") >= 0) { return '"' + data.replace(/"/g, "&quot;") + '"'; }
      return "'" + data + "'";
    }
    return '"' + data + '"';
  }

  // Non-ASCII characters as XML character references.
  function asciiOnly(text) {
    var out = "";
    for (var i = 0; i < text.length; i++) {
      var code = text.codePointAt(i);
      if (code > 0xffff) { i++; }
      out += code < 128 ? String.fromCharCode(code) : "&#" + code + ";";
    }
    return out;
  }

  function cssClass(prefix, value) {
    return prefix + value.replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
  }

  function fontFamily(families) {
    return families.map(function (f) { return f.indexOf(" ") >= 0 ? "'" + f + "'" : f; }).join(", ");
  }

  function color(c) { return c === null || c === undefined ? "none" : c; }

  function textAttrs(style) {
    var f = style.font;
    var attrs = "font-family=" + xmlAttr(fontFamily(f.family)) + ' font-size="' + px(f.size_pt) + '" font-weight="' + f.weight +
      '" font-style="' + f.style + '" fill="' + color(style.color) + '" fill-opacity="' + num(style.alpha) + '"';
    if (style.halo_color && style.halo_width_pt > 0) {
      attrs += ' stroke="' + style.halo_color + '" stroke-width="' + px(2 * style.halo_width_pt) + '" stroke-opacity="' + num(style.alpha) +
        '" stroke-linejoin="round" paint-order="stroke"';
    }
    return attrs;
  }

  function dashPattern(dash, widthPt) {
    if (typeof dash === "string") {
      var scale = Math.max(widthPt, 1.0);
      return DASHES[dash].map(function (v) { return Math.round(v * scale * 1e6) / 1e6; });
    }
    return dash.slice();
  }

  function strokeAttrs(c, widthPt, dashPt, alpha, cap, join) {
    var attrs = 'fill="none" stroke="' + color(c) + '" stroke-width="' + px(widthPt) + '" stroke-opacity="' + num(alpha) +
      '" stroke-linecap="' + cap + '" stroke-linejoin="' + join + '"';
    if (dashPt.length) { attrs += ' stroke-dasharray="' + dashPt.map(px).join(",") + '"'; }
    return attrs;
  }

  function markerShape(shape, x, y, r) {
    var X = num(x), Y = num(y);
    if (shape === "o") { return '<circle cx="' + X + '" cy="' + Y + '" r="' + num(r) + '"/>'; }
    if (shape === "s") { return '<rect x="' + num(x - r) + '" y="' + num(y - r) + '" width="' + num(2 * r) + '" height="' + num(2 * r) + '"/>'; }
    var points = { "^": [[0, -r], [r, r], [-r, r]], v: [[0, r], [r, -r], [-r, -r]], D: [[0, -r], [r, 0], [0, r], [-r, 0]] }[shape];
    if (points) {
      return '<path d="M' + points.map(function (p) { return num(x + p[0]) + "," + num(y + p[1]); }).join("L") + 'Z"/>';
    }
    if (shape === "x") {
      return '<path d="M' + num(x - r) + "," + num(y - r) + "L" + num(x + r) + "," + num(y + r) + "M" + num(x - r) + "," + num(y + r) + "L" +
        num(x + r) + "," + num(y - r) + '"/>';
    }
    if (shape === "+") {
      return '<path d="M' + num(x - r) + "," + Y + "L" + num(x + r) + "," + Y + "M" + X + "," + num(y - r) + "L" + X + "," + num(y + r) + '"/>';
    }
    throw new Error("Unknown marker shape " + shape);
  }

  function fraction(v, lo, hi, log) {
    if (v === null || !isFinite(v)) { return NaN; }
    if (log) { return v > 0 ? (Math.log10(v) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo)) : NaN; }
    return (v - lo) / (hi - lo);
  }

  function drawableLimits(limits, log) {
    var lo = Math.min(limits[0], limits[1]), hi = Math.max(limits[0], limits[1]);
    if (log) {
      if (!(hi > 0)) { hi = 10.0; }
      if (!(lo > 0)) { lo = hi * 1e-3; }
      if (lo === hi) { lo /= 10.0; hi *= 10.0; }
    } else if (lo === hi) {
      var pad = Math.abs(lo) * 0.1 || 0.5;
      lo -= pad; hi += pad;
    }
    return [lo, hi];
  }

  function value(v) { return v === null ? NaN : v; }

  // The writer --------------------------------------------------------------

  function toSvg(scene, options) {
    options = options || {};
    var width = options.width || 800, height = options.height || 600;
    var margins = options.margins || [80, 20, 40, 60];
    var prefix = String(options.idPrefix === undefined ? "coolplot" : options.idPrefix).replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
    var idPrefix = /^[A-Za-z_]/.test(prefix) ? prefix : "cp-" + prefix;
    var axes = scene.axes || {};
    var st = axes.style || defaultAxesStyle();
    var items = (scene.items || []).map(function (item, index) { return { item: item, index: index }; });
    // Drawing order: by z order, then by position (the record is usually in drawing order already)
    items.sort(function (a, b) { return (a.item.z_order - b.item.z_order) || (a.index - b.index); });
    var drawn = items.map(function (e) { return e.item; });
    var xLog = !!axes.x_log, yLog = !!axes.y_log;

    // Legend entries in scene order
    var entries = [];
    (scene.items || []).forEach(function (item) {
      if (!item.legend || !item.visible) { return; }
      var entry = entries.find(function (e) { return e.text === item.legend; });
      if (entry) { entry.items.push(item); } else { entries.push({ text: item.legend, items: [item] }); }
    });
    var legend = st.legend;
    var legendShown = legend.visible && entries.length > 0;
    function legendChars() {
      var sizePx = legend.text.font.size_pt * PX_PER_PT;
      return Math.max(4, Math.floor((0.4 * width - 44.0) / (0.6 * sizePx)));
    }
    function legendText(text) {
      var limit = legendChars();
      // Lengths in characters (code points), not UTF-16 units, as in Python
      var chars = Array.from(text);
      return chars.length <= limit ? text : chars.slice(0, limit - 3).join("") + "...";
    }
    function legendSize() {
      if (!legendShown) { return [0, 0]; }
      var sizePx = legend.text.font.size_pt * PX_PER_PT;
      var longest = Math.max.apply(null, entries.map(function (e) { return Array.from(legendText(e.text)).length; }));
      return [44.0 + 0.6 * sizePx * longest, 8.0 + 1.6 * sizePx * entries.length];
    }

    // Limits
    function dataLimits(key, log) {
      var lo = Infinity, hi = -Infinity, any = false;
      drawn.forEach(function (item) {
        if (!item.visible || item.type === "text") { return; }
        item[key].forEach(function (v) {
          if (v === null || !isFinite(v) || (log && !(v > 0))) { return; }
          lo = Math.min(lo, v); hi = Math.max(hi, v); any = true;
        });
      });
      if (!any) { return log ? [1.0, 10.0] : [0.0, 1.0]; }
      return [lo, hi];
    }
    var xl = drawableLimits(axes.x_limits || dataLimits("x", xLog), xLog);
    var yl = drawableLimits(axes.y_limits || dataLimits("y", yLog), yLog);
    var x0 = xl[0], x1 = xl[1], y0 = yl[0], y1 = yl[1];

    // Room for unclipped text outside the frame
    function textExtent(item) {
      var sizePx = item.style.font.size_pt * PX_PER_PT;
      var length = 0.6 * sizePx * Array.from(item.text).length, h = 1.25 * sizePx;
      var vertical = item.direction && Math.abs(item.direction[1]) > Math.abs(item.direction[0]);
      var along = { left: [0, length], center: [length / 2, length / 2], right: [length, 0] }[item.style.h_align];
      var across = { bottom: [0, h], center: [h / 2, h / 2], top: [h, 0] }[item.style.v_align];
      if (vertical) { return [across[1], across[0], along[0], along[1]]; }
      return [along[0], along[1], across[0], across[1]];
    }
    var need = [0, 0, 0, 0];
    drawn.forEach(function (item) {
      if (!(item.type === "text" && item.visible && item.clip === false)) { return; }
      var fx = fraction(value(item.x), x0, x1, xLog), fy = fraction(value(item.y), y0, y1, yLog);
      if (!(isFinite(fx) && isFinite(fy))) { return; }
      var e = textExtent(item);
      var dx = item.offset_pt[0] * PX_PER_PT, dy = item.offset_pt[1] * PX_PER_PT;
      var reach = [e[0] - dx + 4.0, e[1] + dx + 4.0, e[3] + dy + 4.0, e[2] - dy + 4.0];
      var touches = [fx <= 1e-9, fx >= 1.0 - 1e-9, fy >= 1.0 - 1e-9, fy <= 1e-9];
      for (var k = 0; k < 4; k++) { need[k] = Math.max(need[k], touches[k] ? reach[k] : 0); }
    });
    var extra = need.map(function (n, k) { return Math.max(0, n - margins[k]); });

    // The plot area
    var left = margins[0] + extra[0], right = margins[1] + extra[1], top = margins[2] + extra[2], bottom = margins[3] + extra[3];
    if (legend.location === "outside right") {
      var lw = legendSize()[0];
      right += lw ? lw + 12.0 : 0.0;
    }
    var bw = Math.max(width - left - right, 0.25 * width), bh = Math.max(height - top - bottom, 0.25 * height);
    var bx = left, by = top;
    function toPxX(x) { return bx + fraction(x, x0, x1, xLog) * bw; }
    function toPxY(y) { return by + bh - fraction(y, y0, y1, yLog) * bh; }

    function open(item, extraAttrs) {
      var classes = ["cp-item"];
      if (item.role) { classes.push(cssClass("cp-role-", item.role)); }
      if (item.group) { classes.push(cssClass("cp-group-", item.group)); }
      var more = extraAttrs || "";
      var clips = item.type === "text" ? item.clip !== false : true;
      if (clips) { more = ' clip-path="url(#' + idPrefix + '-plot-area)"' + more; }
      return "<g data-item=" + xmlAttr(item.id) + ' class="' + classes.join(" ") + '"' + more + ">";
    }

    function lineElement(item) {
      var s = item.style, d = "", penDown = false;
      for (var i = 0; i < item.x.length; i++) {
        var x = toPxX(value(item.x[i])), y = toPxY(value(item.y[i]));
        if (!(isFinite(x) && isFinite(y))) { penDown = false; continue; }
        d += (penDown ? "L" : "M") + num(x) + "," + num(y);
        penDown = true;
      }
      var dash = dashPattern(s.dash, s.width_pt);
      var out = open(item);
      if (s.casing_color && s.casing_width_pt > 0) {
        out += '<path class="cp-casing" d="' + d + '" ' + strokeAttrs(s.casing_color, s.width_pt + 2 * s.casing_width_pt, dash, s.alpha, s.cap, s.join) + "/>";
      }
      return out + '<path class="cp-stroke" d="' + d + '" ' + strokeAttrs(s.color, s.width_pt, dash, s.alpha, s.cap, s.join) + "/></g>";
    }

    function markersElement(item) {
      var s = item.style, r = s.size_pt * PX_PER_PT / 2.0;
      var face = (s.shape === "x" || s.shape === "+" || !s.face_color) ? "none" : s.face_color;
      var shapes = "";
      for (var i = 0; i < item.x.length; i++) {
        var x = toPxX(value(item.x[i])), y = toPxY(value(item.y[i]));
        if (isFinite(x) && isFinite(y)) { shapes += markerShape(s.shape, x, y, r); }
      }
      var extraAttrs = ' fill="' + face + '" stroke="' + color(s.edge_color) + '" stroke-width="' + px(s.edge_width_pt) + '" opacity="' +
        num(s.alpha) + '" data-shape=' + xmlAttr(s.shape) + ' data-size-pt="' + num(s.size_pt) + '"';
      return open(item, extraAttrs) + shapes + "</g>";
    }

    function textElement(item) {
      var tx = value(item.x), ty = value(item.y);
      if (!(isFinite(tx) && isFinite(ty))) { return ""; }
      var x = toPxX(tx), y = toPxY(ty);
      if (!(isFinite(x) && isFinite(y))) { return ""; }
      var ox = item.offset_pt[0] * PX_PER_PT, oy = -item.offset_pt[1] * PX_PER_PT;
      var angle = 0.0;
      if (item.direction) {
        var qx = toPxX(tx + item.direction[0] * 1e-3), qy = toPxY(ty + item.direction[1] * 1e-3);
        if (isFinite(qx) && isFinite(qy) && !(qx === x && qy === y)) {
          angle = Math.atan2(qy - y, qx - x) * 180.0 / Math.PI;
          if (angle >= 90.0) { angle -= 180.0; } else if (angle < -90.0) { angle += 180.0; }
        }
      }
      var s = item.style;
      var anchor = { left: "start", center: "middle", right: "end" }[s.h_align];
      var baseline = { bottom: "text-after-edge", center: "central", top: "text-before-edge" }[s.v_align];
      var X = num(x + ox), Y = num(y + oy);
      return open(item) + '<text x="' + X + '" y="' + Y + '" text-anchor="' + anchor + '" dominant-baseline="' + baseline +
        '" transform="rotate(' + num(angle) + " " + X + " " + Y + ')" ' + textAttrs(s) + ">" + xmlText(item.text) + "</text></g>";
    }

    function element(item) {
      if (!item.visible) { return ""; }
      if (item.type === "line") { return lineElement(item); }
      if (item.type === "markers") { return markersElement(item); }
      return textElement(item);
    }

    var lines = [];
    var clip = idPrefix + "-plot-area";
    lines.push('<svg xmlns="http://www.w3.org/2000/svg" width="' + width + '" height="' + height + '" viewBox="0 0 ' + width + " " + height +
      '" data-x-log="' + (xLog ? 1 : 0) + '" data-y-log="' + (yLog ? 1 : 0) + '" data-x-limits="' + reprNumber(x0) + " " + reprNumber(x1) +
      '" data-y-limits="' + reprNumber(y0) + " " + reprNumber(y1) + '">');
    lines.push('<rect class="cp-figure" width="100%" height="100%" fill="' + color(st.figure_background) + '"/>');
    lines.push('<defs><clipPath id="' + clip + '"><rect x="' + num(bx) + '" y="' + num(by) + '" width="' + num(bw) + '" height="' + num(bh) +
      '"/></clipPath></defs>');
    lines.push('<rect class="cp-background" x="' + num(bx) + '" y="' + num(by) + '" width="' + num(bw) + '" height="' + num(bh) + '" fill="' +
      color(st.background) + '"/>');
    [["minor", st.grid_minor], ["major", st.grid_major]].forEach(function (level) {
      var g = level[1];
      if (!g) { return; }
      var attrs = strokeAttrs(g.color, g.width_pt, dashPattern(g.dash, g.width_pt), g.alpha, g.cap, g.join);
      ticks(x0, x1, xLog, level[0] === "minor").forEach(function (v) {
        var p = num(toPxX(v));
        lines.push('<line class="cp-grid-' + level[0] + '" x1="' + p + '" y1="' + num(by) + '" x2="' + p + '" y2="' + num(by + bh) + '" ' + attrs + "/>");
      });
      ticks(y0, y1, yLog, level[0] === "minor").forEach(function (v) {
        var p = num(toPxY(v));
        lines.push('<line class="cp-grid-' + level[0] + '" x1="' + num(bx) + '" y1="' + p + '" x2="' + num(bx + bw) + '" y2="' + p + '" ' + attrs + "/>");
      });
    });
    lines.push('<g class="cp-items">');
    drawn.forEach(function (item) { var e = element(item); if (e) { lines.push(e); } });
    lines.push("</g>");
    lines.push('<rect class="cp-frame" x="' + num(bx) + '" y="' + num(by) + '" width="' + num(bw) + '" height="' + num(bh) +
      '" fill="none" stroke="' + color(st.frame_color) + '" stroke-width="' + px(st.frame_width_pt) + '"/>');
    // Ticks and labels
    var length = st.tick_length_pt * PX_PER_PT * (st.tick_direction === "out" ? 1.0 : -1.0);
    var tick = 'stroke="' + color(st.tick_color) + '" stroke-width="' + px(st.tick_width_pt) + '"';
    var labelAttrs = textAttrs(st.tick_label);
    var gap = st.tick_direction === "out" ? Math.abs(length) : 0.0;
    var digits = axes.tick_digits || 6;
    ticks(x0, x1, xLog, false).forEach(function (v) {
      var p = num(toPxX(v));
      lines.push('<line class="cp-tick cp-tick-x" x1="' + p + '" y1="' + num(by + bh) + '" x2="' + p + '" y2="' + num(by + bh + length) + '" ' + tick + "/>");
      lines.push('<text class="cp-tick-label cp-tick-label-x" x="' + p + '" y="' + num(by + bh + gap + 3.0) +
        '" text-anchor="middle" dominant-baseline="text-before-edge" data-value="' + reprNumber(v) + '" ' + labelAttrs + ">" + formatNumber(v, digits) + "</text>");
    });
    ticks(y0, y1, yLog, false).forEach(function (v) {
      var p = num(toPxY(v));
      lines.push('<line class="cp-tick cp-tick-y" x1="' + num(bx) + '" y1="' + p + '" x2="' + num(bx - length) + '" y2="' + p + '" ' + tick + "/>");
      lines.push('<text class="cp-tick-label cp-tick-label-y" x="' + num(bx - gap - 3.0) + '" y="' + p +
        '" text-anchor="end" dominant-baseline="central" data-value="' + reprNumber(v) + '" ' + labelAttrs + ">" + formatNumber(v, digits) + "</text>");
    });
    lines.push('<text class="cp-x-label" x="' + num(bx + bw / 2.0) + '" y="' + num(height - 8.0) +
      '" text-anchor="middle" dominant-baseline="text-after-edge" ' + textAttrs(st.axis_label) + ">" + xmlText(axes.x_label || "") + "</text>");
    var ymid = num(by + bh / 2.0);
    lines.push('<text class="cp-y-label" x="18" y="' + ymid + '" text-anchor="middle" dominant-baseline="central" transform="rotate(-90 18 ' + ymid +
      ')" ' + textAttrs(st.axis_label) + ">" + xmlText(axes.y_label || "") + "</text>");
    if (axes.title) {
      lines.push('<text class="cp-title" x="' + num(bx + bw / 2.0) + '" y="' + num(by - 8.0 - extra[2]) +
        '" text-anchor="middle" dominant-baseline="text-after-edge" ' + textAttrs(st.title) + ">" + xmlText(axes.title) + "</text>");
    }
    // Legend
    var size = legendSize();
    if (size[0]) {
      var pad = 8.0;
      var lx = { "upper left": bx + pad, "lower left": bx + pad, "upper right": bx + bw - pad - size[0],
                 "lower right": bx + bw - pad - size[0], "outside right": bx + bw + 12.0 }[legend.location];
      var upper = ["upper left", "upper right", "outside right"].indexOf(legend.location) >= 0;
      var ly = upper ? by + pad : by + bh - pad - size[1];
      var sizePx = legend.text.font.size_pt * PX_PER_PT;
      lines.push('<g class="cp-legend">');
      lines.push('<rect class="cp-legend-box" x="' + num(lx) + '" y="' + num(ly) + '" width="' + num(size[0]) + '" height="' + num(size[1]) +
        '" fill="' + color(legend.background) + '" stroke="' + color(legend.frame_color) + '"/>');
      entries.forEach(function (entry, i) {
        var cy = ly + 4.0 + sizePx * (1.6 * i + 0.8);
        lines.push('<g class="cp-legend-entry">');
        entry.items.forEach(function (item) {
          var s = item.style;
          if (item.type === "line") {
            var dash = dashPattern(s.dash, s.width_pt);
            if (s.casing_color && s.casing_width_pt > 0) {
              lines.push('<line class="cp-casing" x1="' + num(lx + 6.0) + '" y1="' + num(cy) + '" x2="' + num(lx + 28.0) + '" y2="' + num(cy) + '" ' +
                strokeAttrs(s.casing_color, s.width_pt + 2 * s.casing_width_pt, dash, s.alpha, s.cap, s.join) + "/>");
            }
            lines.push('<line x1="' + num(lx + 6.0) + '" y1="' + num(cy) + '" x2="' + num(lx + 28.0) + '" y2="' + num(cy) + '" ' +
              strokeAttrs(s.color, s.width_pt, dash, s.alpha, s.cap, s.join) + "/>");
          } else if (item.type === "markers") {
            var face = (s.shape === "x" || s.shape === "+" || !s.face_color) ? "none" : s.face_color;
            lines.push('<g class="cp-legend-marker" fill="' + face + '" stroke="' + color(s.edge_color) + '" stroke-width="' + px(s.edge_width_pt) +
              '" opacity="' + num(s.alpha) + '">' + markerShape(s.shape, lx + 17.0, cy, s.size_pt * PX_PER_PT / 2.0) + "</g>");
          }
        });
        lines.push('<text class="cp-legend-text" x="' + num(lx + 34.0) + '" y="' + num(cy) + '" dominant-baseline="central" ' + textAttrs(legend.text) +
          ">" + xmlText(legendText(entry.text)) + "</text></g>");
      });
      lines.push("</g>");
    }
    lines.push("</svg>");
    return asciiOnly(lines.join("\n"));
  }

  function defaultAxesStyle() {
    var font = function (size, weight) { return { family: ["DejaVu Sans", "Helvetica", "Arial", "sans-serif"], size_pt: size, weight: weight || "normal", style: "normal", files: [] }; };
    var text = function (size, weight) { return { font: font(size, weight), color: "#000000", alpha: 1.0, h_align: "center", v_align: "center", halo_color: null, halo_width_pt: 0.0 }; };
    return {
      background: "#ffffff", figure_background: "#ffffff", frame_color: "#000000", frame_width_pt: 0.8, tick_color: "#000000",
      tick_length_pt: 3.5, tick_width_pt: 0.8, tick_direction: "out", tick_label: text(9.0), axis_label: text(10.0), title: text(11.0, "bold"),
      grid_major: { color: "#dddddd", width_pt: 0.5, dash: "solid", alpha: 1.0, cap: "butt", join: "round", casing_color: null, casing_width_pt: 0.0 },
      grid_minor: null,
      legend: { visible: true, location: "outside right", background: "#ffffff", frame_color: null, text: text(9.0) }
    };
  }

  var api = { toSvg: toSvg, formatNumber: formatNumber, reprNumber: reprNumber, ticks: ticks, num: num };
  if (typeof module === "object" && module.exports) { module.exports = api; } else { root.CoolPlotScene = api; }
})(typeof window !== "undefined" ? window : this);
