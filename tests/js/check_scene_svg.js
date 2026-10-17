// Node check of src/coolplot/render/static/scene_svg.js against the golden
// SVG files in cpp/tests/data (written by the Python writer). Run by
// tests/test_scene_js.py; prints the first difference and exits 1 on one.
"use strict";
var fs = require("fs");
var path = require("path");
var root = path.resolve(__dirname, "..", "..");
var lib = require(path.join(root, "src", "coolplot", "render", "static", "scene_svg.js"));
var data = path.join(root, "cpp", "tests", "data");

function read(name) { return fs.readFileSync(path.join(data, name), "ascii"); }
function json(name) { return JSON.parse(read(name)); }

var failures = 0;
function check(name, made) {
  var expected = read(name);
  if (made === expected) { return; }
  failures++;
  var a = made.split("\n"), b = expected.split("\n");
  for (var i = 0; i < Math.max(a.length, b.length); i++) {
    if (a[i] !== b[i]) {
      console.log(name + ": line " + (i + 1) + "\n  made:     " + String(a[i]).slice(0, 200) + "\n  expected: " + String(b[i]).slice(0, 200));
      return;
    }
  }
}

var conformance = json("conformance_scene.json");
check("conformance_scene.svg", lib.toSvg(conformance));
check("conformance_scene_small.svg", lib.toSvg(conformance, { width: 640, height: 480, margins: [50, 10, 30, 40], idPrefix: "2 charts/one page" }));
["upper left", "lower right"].forEach(function (location) {
  var moved = JSON.parse(JSON.stringify(conformance));
  moved.axes.style.legend.location = location;
  check("conformance_legend_" + location.replace(" ", "_") + ".svg", lib.toSvg(moved));
});
var axes = { y_log: true };
check("autoscale.svg", lib.toSvg({ axes: autoAxes(true, null, null), items: [
  item("line", "a", [1, 2, 3], [0.5, 5, 50], true),
  item("markers", "b", [4], [null], true),
  item("line", "hidden", [-100, 1000], [1e-6, 1e9], false)] }));
check("narrow_log.svg", lib.toSvg({ axes: autoAxes(true, [1.5, 1.9], [1.5, 1.9]), items: [item("line", "a", [1.5, 1.9], [1.5, 1.9], true)] }));
["compose_r290_ph", "compose_r290_ph_sized", "compose_blend_ts_margin", "compose_r290_hs_inline", "compose_psychrometric"].forEach(function (name) {
  check(name + ".svg", lib.toSvg(json(name + ".json").scene));
});

function autoAxes(yLog, xLimits, yLimits) {
  var a = JSON.parse(JSON.stringify(conformance.axes));
  var defaults = { x_label: "", y_label: "", x_log: false, y_log: yLog, x_limits: xLimits, y_limits: yLimits, title: "", tick_digits: 6 };
  Object.keys(defaults).forEach(function (k) { a[k] = defaults[k]; });
  a.style = null;
  return a;
}
function item(type, id, x, y, visible) {
  var style = type === "line"
    ? { color: "#000000", width_pt: 1.0, dash: "solid", alpha: 1.0, cap: "butt", join: "round", casing_color: null, casing_width_pt: 0.0 }
    : { shape: "o", size_pt: 6.0, face_color: "#000000", edge_color: "#000000", edge_width_pt: 1.0, alpha: 1.0 };
  return { type: type, id: id, group: "", role: "", legend: null, visible: visible, z_order: 1.0, style: style, x: x, y: y };
}

if (failures) { console.log(failures + " file(s) differ"); process.exit(1); }
console.log("all files identical");
