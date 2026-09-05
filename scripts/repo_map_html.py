#!/usr/bin/env python3
"""Render a repo_map.Report into one self-contained HTML page.

No CDN, no external stylesheet, no network access at view time: the data is
embedded as JSON and the page builds itself from it. That keeps the report
usable offline and makes it safe to open straight from disk.
"""
from __future__ import annotations

import json

from repo_map import DirNode, Report
from repo_map_metrics import FileEntry

# Score at which a file is called out as a split candidate.
CANDIDATE_SCORE = 1


def build_payload(report: Report) -> dict:
    """Turn a report into the plain-data structure the page renders from.

    Files come out ordered by score, then by size - that ordering IS the work
    list, so it belongs in the data rather than in the browser.
    """
    files = sorted(report.entries, key=lambda e: (-e.score, -e.loc, e.path))
    return {
        "commit": report.commit,
        "generatedAt": report.generated_at,
        "thresholds": {
            "max_loc": report.thresholds.max_loc,
            "max_fn_loc": report.thresholds.max_fn_loc,
            "max_depth": report.thresholds.max_depth,
        },
        "totals": _totals(report.entries),
        "tree": _tree_payload(report.tree),
        "files": [_file_payload(entry) for entry in files],
    }


def _totals(entries: list[FileEntry]) -> dict:
    return {
        "files": len(entries),
        "loc": sum(e.loc for e in entries),
        "code": sum(e.code for e in entries),
        "comment": sum(e.comment for e in entries),
        "blank": sum(e.blank for e in entries),
        "candidates": sum(1 for e in entries if e.score >= CANDIDATE_SCORE),
    }


def _file_payload(entry: FileEntry) -> dict:
    return {
        "p": entry.path,
        "e": entry.ext,
        "k": entry.kind,
        "loc": entry.loc,
        "code": entry.code,
        "cm": entry.comment,
        "bl": entry.blank,
        "sym": entry.symbols,
        "cls": entry.classes,
        "fn": entry.functions,
        "hk": entry.hooks,
        "ln": entry.longest_name,
        "ll": entry.longest_loc,
        "d": entry.max_depth,
        "est": entry.estimated,
        "gen": entry.generated,
        "s": entry.score,
        "r": list(entry.reasons),
    }


def _tree_payload(node: DirNode) -> dict:
    children = sorted(node.children.values(), key=lambda c: (-c.loc, c.name))
    return {
        "name": node.name,
        "path": node.path,
        "loc": node.loc,
        "files": node.files,
        "children": [_tree_payload(child) for child in children],
    }


def _embed(payload: dict) -> str:
    """Serialise the payload so it cannot terminate its own script element.

    Escaping the angle brackets keeps a path like `weird/</script>` from
    closing the tag early - the browser still parses it as valid JSON.
    """
    return (
        json.dumps(payload, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def render(report: Report) -> str:
    """Render the full HTML document for a report."""
    return _TEMPLATE.replace("__PAYLOAD__", _embed(build_payload(report)))


_STYLE = """
:root {
  color-scheme: dark;
  --bg: #14161a; --panel: #1c1f26; --line: #2c313b;
  --fg: #e6e8ec; --muted: #8d95a5; --accent: #6fa8ff;
  --warn: #f0b429; --hot: #f2686b; --ok: #4fbf7f;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg);
  font: 14px/1.5 "Segoe UI", system-ui, sans-serif; }
header { padding: 24px 28px 16px; border-bottom: 1px solid var(--line); }
h1 { margin: 0 0 4px; font-size: 20px; font-weight: 600; }
h2 { margin: 0 0 12px; font-size: 15px; font-weight: 600; color: var(--muted);
  text-transform: uppercase; letter-spacing: .06em; }
.meta { color: var(--muted); font-size: 12px; }
.cards { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
  padding: 10px 14px; min-width: 120px; }
.card b { display: block; font-size: 19px; font-weight: 600; }
.card span { color: var(--muted); font-size: 11px; text-transform: uppercase;
  letter-spacing: .05em; }
main { padding: 20px 28px 60px; display: grid; gap: 28px; }
section { min-width: 0; }
.tree { font-family: Consolas, "Cascadia Mono", monospace; font-size: 13px; }
.tree details { margin-left: 14px; }
.tree > details { margin-left: 0; }
.tree summary { cursor: pointer; padding: 1px 0; list-style: none;
  display: grid; grid-template-columns: 1fr 90px 70px 160px; gap: 8px;
  align-items: center; }
.tree summary::-webkit-details-marker { display: none; }
.tree summary:hover { background: var(--panel); }
.tree .nm::before { content: "\\25B8 "; color: var(--muted); }
.tree details[open] > summary .nm::before { content: "\\25BE "; }
.tree .num { text-align: right; color: var(--muted); }
.bar { height: 7px; background: var(--line); border-radius: 4px; overflow: hidden; }
.bar > i { display: block; height: 100%; background: var(--accent); }
.leaf { display: grid; grid-template-columns: 1fr 90px 70px 160px; gap: 8px;
  margin-left: 28px; padding: 1px 0; }
.leaf .nm { color: var(--fg); opacity: .8; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--line);
  white-space: nowrap; }
th { position: sticky; top: 0; background: var(--bg); cursor: pointer;
  color: var(--muted); font-weight: 600; user-select: none; }
th.num, td.num { text-align: right; }
th:hover { color: var(--fg); }
td.path { font-family: Consolas, "Cascadia Mono", monospace; white-space: nowrap;
  max-width: 520px; overflow: hidden; text-overflow: ellipsis; }
td.why { white-space: normal; color: var(--muted); font-size: 12px;
  min-width: 260px; }
.wrap { overflow-x: auto; max-height: 70vh; overflow-y: auto;
  border: 1px solid var(--line); border-radius: 8px; }
.pill { display: inline-block; padding: 0 6px; border-radius: 10px;
  font-size: 11px; font-weight: 600; }
.s-hot { background: rgba(242,104,107,.18); color: var(--hot); }
.s-warn { background: rgba(240,180,41,.18); color: var(--warn); }
.s-ok { background: rgba(79,191,127,.15); color: var(--ok); }
.tag { color: var(--muted); font-size: 11px; margin-left: 6px; }
.filters { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
input, select { background: var(--panel); border: 1px solid var(--line);
  color: var(--fg); border-radius: 6px; padding: 5px 9px; font: inherit; }
input:focus, select:focus { outline: 1px solid var(--accent); }
label.chk { display: flex; align-items: center; gap: 6px; color: var(--muted); }
"""

_SCRIPT = """
const DATA = JSON.parse(document.getElementById("repo-map-data").textContent);
const nf = new Intl.NumberFormat("de-DE");
const el = (t, cls, txt) => {
  const n = document.createElement(t);
  if (cls) n.className = cls;
  if (txt !== undefined) n.textContent = txt;
  return n;
};
const scoreClass = (s) => (s >= 60 ? "s-hot" : s >= 25 ? "s-warn" : "s-ok");

function head() {
  const t = DATA.totals, th = DATA.thresholds;
  document.getElementById("meta").textContent =
    `commit ${DATA.commit} \\u00b7 ${DATA.generatedAt} \\u00b7 limits: ` +
    `${th.max_loc} LOC / ${th.max_fn_loc} LOC per function / depth ${th.max_depth}`;
  const cards = [
    ["Files", nf.format(t.files)], ["Lines", nf.format(t.loc)],
    ["Code", nf.format(t.code)], ["Comments", nf.format(t.comment)],
    ["Blank", nf.format(t.blank)], ["Flagged", nf.format(t.candidates)],
  ];
  const box = document.getElementById("cards");
  for (const [label, value] of cards) {
    const c = el("div", "card");
    c.append(el("b", null, value), el("span", null, label));
    box.append(c);
  }
}

function treeRow(name, loc, files, share, isLeaf) {
  const frag = document.createDocumentFragment();
  frag.append(el("span", "nm", name));
  frag.append(el("span", "num", nf.format(loc)));
  frag.append(el("span", "num", files === null ? "" : nf.format(files)));
  const bar = el("div", "bar");
  const fill = el("i");
  fill.style.width = Math.max(1, Math.round(share * 100)) + "%";
  if (isLeaf) fill.style.background = "var(--muted)";
  bar.append(fill);
  frag.append(bar);
  return frag;
}

function renderTree(node, parent, total, depth) {
  const build = (n, host, lvl) => {
    const d = el("details");
    if (lvl < 1) d.open = true;
    const s = el("summary");
    s.append(treeRow(n.name || "/", n.loc, n.files, total ? n.loc / total : 0, false));
    d.append(s);
    for (const child of n.children) build(child, d, lvl + 1);
    const own = DATA.files.filter((f) => {
      const cut = f.p.lastIndexOf("/");
      return (cut === -1 ? "" : f.p.slice(0, cut)) === n.path;
    }).sort((a, b) => b.loc - a.loc);
    for (const f of own) {
      const row = el("div", "leaf");
      row.append(treeRow(f.p.split("/").pop(), f.loc, null,
        total ? f.loc / total : 0, true));
      d.append(row);
    }
    host.append(d);
  };
  build(node, parent, depth);
}

const COLUMNS = [
  { key: "p", label: "File", cls: "path" },
  { key: "s", label: "Score", num: true },
  { key: "loc", label: "LOC", num: true },
  { key: "code", label: "Code", num: true },
  { key: "sym", label: "Symbols", num: true },
  { key: "ll", label: "Longest", num: true },
  { key: "d", label: "Depth", num: true },
  { key: "r", label: "Why", cls: "why" },
];
let sortKey = "s", sortDir = -1;

function cell(f, col) {
  if (col.key === "p") {
    const td = el("td", "path");
    td.append(document.createTextNode(f.p));
    if (f.est) td.append(el("span", "tag", "est."));
    if (f.gen) td.append(el("span", "tag", "generated"));
    return td;
  }
  if (col.key === "s") {
    const td = el("td", "num");
    td.append(el("span", "pill " + scoreClass(f.s), String(f.s)));
    return td;
  }
  if (col.key === "r") {
    const parts = f.r.slice();
    if (f.ln && f.ll) parts.push(`longest: ${f.ln}`);
    return el("td", "why", parts.join(" \\u00b7 "));
  }
  return el("td", "num", nf.format(f[col.key] || 0));
}

function renderTable() {
  const q = document.getElementById("q").value.trim().toLowerCase();
  const ext = document.getElementById("ext").value;
  const onlyFlagged = document.getElementById("flagged").checked;
  const hideGen = document.getElementById("hidegen").checked;

  const rows = DATA.files.filter((f) =>
    (!q || f.p.toLowerCase().includes(q)) &&
    (!ext || f.e === ext) &&
    (!onlyFlagged || f.s > 0) &&
    (!hideGen || !f.gen)
  ).sort((a, b) => {
    const x = a[sortKey], y = b[sortKey];
    if (typeof x === "string") return x.localeCompare(y) * sortDir;
    return ((x || 0) - (y || 0)) * sortDir;
  });

  const body = document.getElementById("rows");
  body.textContent = "";
  document.getElementById("count").textContent =
    `${nf.format(rows.length)} of ${nf.format(DATA.files.length)} files`;
  const frag = document.createDocumentFragment();
  for (const f of rows) {
    const tr = el("tr");
    for (const col of COLUMNS) tr.append(cell(f, col));
    frag.append(tr);
  }
  body.append(frag);
}

function buildTable() {
  const tr = document.getElementById("headrow");
  for (const col of COLUMNS) {
    const th = el("th", col.num ? "num" : null, col.label);
    th.onclick = () => {
      sortDir = sortKey === col.key ? -sortDir : (col.key === "p" ? 1 : -1);
      sortKey = col.key;
      renderTable();
    };
    tr.append(th);
  }
  const exts = [...new Set(DATA.files.map((f) => f.e))].sort();
  const sel = document.getElementById("ext");
  for (const e of exts) sel.append(new Option(e || "(none)", e));
  for (const id of ["q", "ext", "flagged", "hidegen"]) {
    document.getElementById(id).addEventListener("input", renderTable);
  }
  renderTable();
}

head();
renderTree(DATA.tree, document.getElementById("tree"), DATA.totals.loc, 0);
buildTable();
"""

_TEMPLATE = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BaluHost Repo Map</title>
<style>{_STYLE}</style>
</head>
<body>
<header>
  <h1>BaluHost Repo Map</h1>
  <div class="meta" id="meta"></div>
  <div class="cards" id="cards"></div>
</header>
<main>
  <section>
    <h2>Directories</h2>
    <div class="tree" id="tree"></div>
  </section>
  <section>
    <h2>Files &mdash; sorted by refactor score</h2>
    <div class="filters">
      <input id="q" type="search" placeholder="filter by path…" size="34">
      <select id="ext"><option value="">all extensions</option></select>
      <label class="chk"><input id="flagged" type="checkbox"> only flagged</label>
      <label class="chk"><input id="hidegen" type="checkbox"> hide generated</label>
      <span class="meta" id="count"></span>
    </div>
    <div class="wrap">
      <table>
        <thead><tr id="headrow"></tr></thead>
        <tbody id="rows"></tbody>
      </table>
    </div>
  </section>
</main>
<script type="application/json" id="repo-map-data">__PAYLOAD__</script>
<script>{_SCRIPT}</script>
</body>
</html>
"""
