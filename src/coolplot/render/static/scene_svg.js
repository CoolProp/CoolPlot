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

  // Exact tests on numbers without comparing two numbers for equality (the
  // same helpers as coolplot/core/floats.py): isZero classifies the bits of
  // the double, sameNumber says whether two values are the very number set or
  // copied earlier (the same bits, or +0 and -0; NaN is no number).
  // A DataView fixes the byte order (big-endian), whatever the machine uses.
  var floatView = new DataView(new ArrayBuffer(8));
  function isZero(value) {
    floatView.setFloat64(0, value);
    return (floatView.getUint32(0) & 0x7fffffff) === 0 && floatView.getUint32(4) === 0;
  }
  function sameNumber(a, b) {
    if (isNaN(a) || isNaN(b)) { return false; }
    if (isZero(a) && isZero(b)) { return true; }
    floatView.setFloat64(0, a);
    var high = floatView.getUint32(0), low = floatView.getUint32(4);
    floatView.setFloat64(0, b);
    return high === floatView.getUint32(0) && low === floatView.getUint32(4);
  }

  // value.toFixed(decimals), rounded half to even and without exponent.
  function toFixedEven(value, decimals) {
    var abs = Math.abs(value);
    if (abs >= 1e21) {
      return (value < 0 ? "-" : "") + BigInt(abs).toString() + (decimals > 0 ? "." + "0".repeat(decimals) : "");
    }
    if (!isZero(value) && tieRoundsDown(abs, decimals)) { value = towardZero(value); }
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
    if (isZero(value)) { return (1 / value < 0) ? "-0.0" : "0.0"; }
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
    if (isZero(value)) { return "0"; }
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
      if (sameNumber(lo, hi)) { lo /= 10.0; hi *= 10.0; }
    } else if (sameNumber(lo, hi)) {
      var pad = Math.abs(lo) * 0.1;
      if (isZero(pad)) { pad = 0.5; }
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
    // With a title the configured top margin holds the title, so labels
    // above the frame need their whole height on top of it
    if (axes.title) { extra[2] = need[2]; }

    // The plot area
    var left = margins[0] + extra[0], right = margins[1] + extra[1], top = margins[2] + extra[2], bottom = margins[3] + extra[3];
    if (legend.location === "outside right") {
      var lw = legendSize()[0];
      right += (isZero(lw) || isNaN(lw)) ? 0.0 : lw + 12.0;   // NaN counts as no legend, as before
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
        if (isFinite(qx) && isFinite(qy) && !(sameNumber(qx, x) && sameNumber(qy, y))) {
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
    if (axes.badge) { Array.prototype.push.apply(lines, badgeElements(axes.badge, bx, by, bw, bh)); }
    // Legend
    var size = legendSize();
    if (!(isZero(size[0]) || isNaN(size[0]))) {
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

  // Text width (coolplot.core.textwidth) -----------------------------------

  // Advance widths in 1/1000 em of the characters " " (32) to "~" (126), Helvetica
  var HELVETICA_WIDTHS = [
    278, 278, 355, 556, 556, 889, 667, 222, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556,
    556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667,
    611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667,
    667, 611, 278, 278, 278, 469, 556, 222, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500,
    222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584
  ];
  // The code points Python's unicodedata.east_asian_width calls "W" or "F" (Unicode 15.1), as sorted ranges
  var WIDE_RANGES = [
    [0x1100, 0x115F], [0x231A, 0x231B], [0x2329, 0x232A], [0x23E9, 0x23EC], [0x23F0, 0x23F0], [0x23F3, 0x23F3], [0x25FD, 0x25FE], [0x2614, 0x2615],
    [0x2648, 0x2653], [0x267F, 0x267F], [0x2693, 0x2693], [0x26A1, 0x26A1], [0x26AA, 0x26AB], [0x26BD, 0x26BE], [0x26C4, 0x26C5], [0x26CE, 0x26CE],
    [0x26D4, 0x26D4], [0x26EA, 0x26EA], [0x26F2, 0x26F3], [0x26F5, 0x26F5], [0x26FA, 0x26FA], [0x26FD, 0x26FD], [0x2705, 0x2705], [0x270A, 0x270B],
    [0x2728, 0x2728], [0x274C, 0x274C], [0x274E, 0x274E], [0x2753, 0x2755], [0x2757, 0x2757], [0x2795, 0x2797], [0x27B0, 0x27B0], [0x27BF, 0x27BF],
    [0x2B1B, 0x2B1C], [0x2B50, 0x2B50], [0x2B55, 0x2B55], [0x2E80, 0x2E99], [0x2E9B, 0x2EF3], [0x2F00, 0x2FD5], [0x2FF0, 0x303E], [0x3041, 0x3096],
    [0x3099, 0x30FF], [0x3105, 0x312F], [0x3131, 0x318E], [0x3190, 0x31E3], [0x31EF, 0x321E], [0x3220, 0x3247], [0x3250, 0x4DBF], [0x4E00, 0xA48C],
    [0xA490, 0xA4C6], [0xA960, 0xA97C], [0xAC00, 0xD7A3], [0xF900, 0xFAFF], [0xFE10, 0xFE19], [0xFE30, 0xFE52], [0xFE54, 0xFE66], [0xFE68, 0xFE6B],
    [0xFF01, 0xFF60], [0xFFE0, 0xFFE6], [0x16FE0, 0x16FE4], [0x16FF0, 0x16FF1], [0x17000, 0x187F7], [0x18800, 0x18CD5], [0x18D00, 0x18D08],
    [0x1AFF0, 0x1AFF3], [0x1AFF5, 0x1AFFB], [0x1AFFD, 0x1AFFE], [0x1B000, 0x1B122], [0x1B132, 0x1B132], [0x1B150, 0x1B152], [0x1B155, 0x1B155],
    [0x1B164, 0x1B167], [0x1B170, 0x1B2FB], [0x1F004, 0x1F004], [0x1F0CF, 0x1F0CF], [0x1F18E, 0x1F18E], [0x1F191, 0x1F19A], [0x1F200, 0x1F202],
    [0x1F210, 0x1F23B], [0x1F240, 0x1F248], [0x1F250, 0x1F251], [0x1F260, 0x1F265], [0x1F300, 0x1F320], [0x1F32D, 0x1F335], [0x1F337, 0x1F37C],
    [0x1F37E, 0x1F393], [0x1F3A0, 0x1F3CA], [0x1F3CF, 0x1F3D3], [0x1F3E0, 0x1F3F0], [0x1F3F4, 0x1F3F4], [0x1F3F8, 0x1F43E], [0x1F440, 0x1F440],
    [0x1F442, 0x1F4FC], [0x1F4FF, 0x1F53D], [0x1F54B, 0x1F54E], [0x1F550, 0x1F567], [0x1F57A, 0x1F57A], [0x1F595, 0x1F596], [0x1F5A4, 0x1F5A4],
    [0x1F5FB, 0x1F64F], [0x1F680, 0x1F6C5], [0x1F6CC, 0x1F6CC], [0x1F6D0, 0x1F6D2], [0x1F6D5, 0x1F6D7], [0x1F6DC, 0x1F6DF], [0x1F6EB, 0x1F6EC],
    [0x1F6F4, 0x1F6FC], [0x1F7E0, 0x1F7EB], [0x1F7F0, 0x1F7F0], [0x1F90C, 0x1F93A], [0x1F93C, 0x1F945], [0x1F947, 0x1F9FF], [0x1FA70, 0x1FA7C],
    [0x1FA80, 0x1FA88], [0x1FA90, 0x1FABD], [0x1FABF, 0x1FAC5], [0x1FACE, 0x1FADB], [0x1FAE0, 0x1FAE8], [0x1FAF0, 0x1FAF8], [0x20000, 0x2FFFD],
    [0x30000, 0x3FFFD]
  ];

  function isWide(code) {
    for (var i = 0; i < WIDE_RANGES.length; i++) {
      if (code < WIDE_RANGES[i][0]) { return false; }
      if (code <= WIDE_RANGES[i][1]) { return true; }
    }
    return false;
  }

  // Estimated width of one line of text at sizePt: Helvetica, 15 % wider for wider fonts
  function textWidthPt(text, sizePt) {
    var total = 0.0;
    for (var ch of text) {
      var code = ch.codePointAt(0);
      if (code >= 32 && code <= 126) { total += HELVETICA_WIDTHS[code - 32] / 1000.0; } else { total += isWide(code) ? 1.0 : 0.6; }
    }
    return 1.15 * sizePt * total;
  }

  // The badge of the branding: a box of text lines in a corner (coolplot.render.svg). The record
  // holds its lines and styles; a logo is left out here (its height needs the picture's aspect).
  var BADGE_LINE_HEIGHT = 1.25, BADGE_BASELINE = 0.95;

  function badgeElements(badge, bx, by, bw, bh) {
    var lines = [];
    (badge.lines || []).forEach(function (line) { String(line).replace(/\r\n/g, "\n").split("\n").forEach(function (part) { lines.push(part); }); });
    if (lines.length === 0) { return []; }
    var sizePt = badge.text.font.size_pt, lineHeightPt = BADGE_LINE_HEIGHT * sizePt;
    var textW = 0.0;
    lines.forEach(function (line) { textW = Math.max(textW, textWidthPt(line, sizePt)); });
    var width = (textW + 2.0 * badge.padding_pt) * PX_PER_PT, height = (lines.length * lineHeightPt + 2.0 * badge.padding_pt) * PX_PER_PT;
    var inset = badge.inset_pt * PX_PER_PT;
    var parts = badge.location.split(" ");
    var x = parts[1] === "left" ? bx + inset : bx + bw - inset - width;
    var y = parts[0] === "upper" ? by + inset : by + bh - inset - height;
    var pad = badge.padding_pt * PX_PER_PT;
    var out = ['<g class="cp-badge">',
      '<rect class="cp-badge-box" x="' + num(x) + '" y="' + num(y) + '" width="' + num(width) + '" height="' + num(height) + '" fill="' +
      color(badge.background) + '" fill-opacity="' + num(badge.background_alpha) + '" stroke="' + color(badge.frame_color) +
      '" stroke-width="' + px(badge.frame_color ? badge.frame_width_pt : 0.0) + '"/>'];
    var lineH = lineHeightPt * PX_PER_PT, sizePx = sizePt * PX_PER_PT;
    lines.forEach(function (line, i) {
      out.push('<text class="cp-badge-text" x="' + num(x + pad) + '" y="' + num(y + pad + i * lineH + BADGE_BASELINE * sizePx) +
        '" text-anchor="start" ' + textAttrs(badge.text) + ">" + xmlText(line) + "</text>");
    });
    out.push("</g>");
    return out;
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

  var api = { toSvg: toSvg, formatNumber: formatNumber, reprNumber: reprNumber, ticks: ticks, num: num, textWidthPt: textWidthPt };
  if (typeof module === "object" && module.exports) { module.exports = api; } else { root.CoolPlotScene = api; }
})(typeof window !== "undefined" ? window : this);
