"""JS for the report's history charts and hotspot table.

Split out of repo_map_html.py to keep that file under the repo's own
500-line convention (this task's additions were the largest of the plan and
pushed it over). Pure string constant, embedded verbatim into the page's
inline <script> - no separate load, no module system, still one
self-contained document.

Because this is a plain string concatenated onto repo_map_html._SCRIPT (see
_SCRIPT += HISTORY_SCRIPT there) rather than an importable module, nothing
here is checked by name at import time. This module's JS relies on four
identifiers defined in that other string: DATA (the embedded payload), el
(element-builder helper), nf (the Intl.NumberFormat instance), and
scoreClass (score -> pill-color mapping). Renaming any of them in
repo_map_html.py's _SCRIPT breaks this page at runtime with no Python test
failing - only a browser console error would show it.
"""
from __future__ import annotations

# Three inline-SVG line charts (LOC per area; flagged-file count; score sum,
# each of the last two on its own axis since they differ by ~27x in scale
# and would flatten one another on a shared one) plus a hotspot table (score
# x commits). No chart library: builds SVG nodes directly from DATA.history
# via the DOM API. Colors come from the page's existing dark-theme tokens
# (--accent/--ok/--warn/--hot/--muted) so a chart never introduces a color
# the rest of the report doesn't already use.
HISTORY_SCRIPT = """
const SERIES_COLORS = ["#6fa8ff", "#4fbf7f", "#f0b429", "#f2686b", "#8d95a5"];
const SVG_NS = "http://www.w3.org/2000/svg";

function svg(tag, attrs) {
  const n = document.createElementNS(SVG_NS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  return n;
}

// A "nice" axis step (1/2/2.5/5/10 x a power of ten) so tick labels read as
// round numbers instead of an arbitrary fraction of the raw data max.
function niceStep(rawMax, ticks) {
  const rough = rawMax / ticks;
  const mag = Math.pow(10, Math.floor(Math.log10(rough)));
  for (const m of [1, 2, 2.5, 5, 10]) {
    if (rough <= m * mag) return m * mag;
  }
  return 10 * mag;
}

function lineChart(host, labels, series, fmt) {
  const H = 260, L = 62, R = 12, T = 12, B = 34;
  // Width follows the host's own box in real CSS pixels, so the viewBox
  // maps 1:1 onto rendered pixels and nothing gets stretched horizontally
  // relative to vertical (a fixed viewBox on a percentage-width element,
  // scaled to fit non-uniformly, distorted every glyph and gap - only
  // visible on the text, since the lines themselves still look fine).
  const W = Math.max(360, Math.round(host.clientWidth || 720));
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H,
    role: "img" });
  const rawMax = Math.max(0, ...series.flatMap((s) => s.values));
  const step = niceStep(rawMax > 0 ? rawMax : 1, 4);
  // The axis top follows the data (rounded up to the next step), not a
  // fixed 4-tick span - a max that is much bigger than the data would
  // otherwise waste the top half of the plot on empty space.
  const max = Math.max(step, Math.ceil(rawMax / step) * step);
  const ticks = Math.round(max / step);
  const x = (i) => L + (labels.length < 2 ? 0
    : (i * (W - L - R)) / (labels.length - 1));
  const y = (v) => H - B - (v / max) * (H - T - B);

  for (let g = 0; g <= ticks; g++) {
    const gy = T + (g * (H - T - B)) / ticks;
    root.append(svg("line", { class: "grid", x1: L, x2: W - R, y1: gy, y2: gy }));
    const t = svg("text", { class: "tick", x: L - 8, y: gy + 4,
      "text-anchor": "end" });
    t.textContent = fmt(Math.round(step * (ticks - g)));
    root.append(t);
  }
  root.append(svg("line", { class: "axis", x1: L, x2: W - R,
    y1: H - B, y2: H - B }));

  // Anchor the first/last shown label to start/end instead of middle so
  // neither one runs past the plot edge.
  const shown = labels
    .map((label, i) => ({ label, i }))
    .filter(({ i }) => !(labels.length > 12 && i % 2));
  shown.forEach(({ label, i }, si) => {
    const anchor = si === 0 ? "start" : si === shown.length - 1 ? "end" : "middle";
    const t = svg("text", { class: "lbl", x: x(i), y: H - B + 16,
      "text-anchor": anchor });
    t.textContent = label;
    root.append(t);
  });

  series.forEach((s, si) => {
    const color = SERIES_COLORS[si % SERIES_COLORS.length];
    const d = s.values.map((v, i) => `${i ? "L" : "M"}${x(i)} ${y(v)}`).join(" ");
    root.append(svg("path", { d, fill: "none", stroke: color, "stroke-width": 2 }));
    s.values.forEach((v, i) => {
      const dot = svg("circle", { cx: x(i), cy: y(v), r: 3, fill: color });
      const title = svg("title");
      title.textContent = `${s.name} \\u00b7 ${labels[i]}: ${fmt(v)}`;
      dot.append(title);
      root.append(dot);
    });
  });

  host.textContent = "";
  host.append(root);
}

function legend(host, names) {
  host.textContent = "";
  names.forEach((name, i) => {
    const span = el("span");
    const dot = el("i");
    dot.style.background = SERIES_COLORS[i % SERIES_COLORS.length];
    span.append(dot, document.createTextNode(name));
    host.append(span);
  });
}

function renderHistory() {
  const h = DATA.history;
  if (!h || h.points.length < 2) return;
  document.getElementById("history").hidden = false;

  const labels = h.points.map((p) => p.label);
  const areaSeries = h.areas
    .map((name) => ({ name,
      values: h.points.map((p) => p.areas[name] || 0) }))
    .filter((s) => s.values.some((v) => v > 0));
  legend(document.getElementById("history-legend"),
    areaSeries.map((s) => s.name));
  lineChart(document.getElementById("history-chart"), labels, areaSeries,
    (v) => nf.format(v));

  // Two separate charts, not one shared axis: flagged-file counts (tens to
  // low hundreds) and the score sum (thousands to tens of thousands) live
  // on wildly different scales, so a single shared axis flattens the
  // smaller series into an unreadable near-flat line at the bottom.
  const flagged = [
    { name: "geflaggte Dateien", values: h.points.map((p) => p.flagged) },
  ];
  legend(document.getElementById("flagged-legend"), flagged.map((s) => s.name));
  lineChart(document.getElementById("flagged-chart"), labels, flagged,
    (v) => nf.format(v));

  const scoreSum = [
    { name: "Score-Summe", values: h.points.map((p) => p.score) },
  ];
  legend(document.getElementById("score-legend"), scoreSum.map((s) => s.name));
  lineChart(document.getElementById("score-chart"), labels, scoreSum,
    (v) => nf.format(v));

  const rows = DATA.files
    .filter((f) => f.s > 0 && f.ch > 0)
    .map((f) => ({ f, hot: f.s * f.ch }))
    .sort((a, b) => b.hot - a.hot)
    .slice(0, 25);
  const body = document.getElementById("history-hotspots");
  body.textContent = "";
  for (const { f, hot } of rows) {
    const tr = el("tr");
    tr.append(el("td", "path", f.p));
    const score = el("td", "num " + scoreClass(f.s), String(f.s));
    tr.append(score);
    tr.append(el("td", "num", nf.format(f.loc)));
    tr.append(el("td", "num", nf.format(f.ch)));
    tr.append(el("td", "num", nf.format(hot)));
    tr.append(el("td", "num", f.lt || ""));
    body.append(tr);
  }
}

// The chart width is measured from the host element at render time, so a
// window resize must re-run the chart or it stays sized for the old width.
// renderHistory() is idempotent (every host is cleared before it is
// rebuilt) so calling it again on resize is safe.
let histResizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(histResizeTimer);
  histResizeTimer = setTimeout(renderHistory, 150);
});
"""
