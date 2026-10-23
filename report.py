"""
Builds the single-file HTML report from the screener results.

The page loads Plotly from a CDN, so it needs an internet connection to
draw charts. Everything else (data, styles, scripts) is inside the file.
"""

from __future__ import annotations

import html
import json
import math
from datetime import datetime

import numpy as np
import pandas as pd

import config

PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"

SCORE_COLUMNS = [
    ("peer_value", "Peers now"),
    ("history_value", "Own history"),
    ("dividend_value", "Div. yield history"),
    ("quality", "Quality"),
    ("composite", "Composite"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(obj):
    """Make an object JSON-safe: NaN/inf to None, numpy to Python types."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.strftime("%Y-%m-%d")
    return obj


def _fmt_metric(metric: str, value) -> str:
    if value is None or pd.isna(value):
        return "–"
    kind = config.METRICS[metric]["kind"]
    if kind == "valuation" and value <= 0:
        return "n/m"
    return config.METRICS[metric]["fmt"].format(value).replace("-", "−")


def _fmt_yield(value) -> str:
    if value is None or pd.isna(value):
        return "–"
    return f"{value:.1%}".replace("-", "−")


def _inverse(value) -> float:
    if value is None or pd.isna(value) or value == 0:
        return np.nan
    return 1.0 / value


def _metric_th(metric: str, scope: str = "") -> str:
    spec = config.METRICS[metric]
    scope_attr = f' scope="{scope}"' if scope else ""
    cls = "" if scope else ' class="num"'
    if spec["kind"] != "valuation":
        return f'<th{cls}{scope_attr}>{_esc(spec["label"])}</th>'
    return (f'<th{cls}{scope_attr} data-label-mult="{_esc(spec["label"])}" '
            f'data-label-yield="{_esc(spec["yield_label"])}">{_esc(spec["label"])}</th>')


def _metric_td(metric: str, value, extra_cls: str = "", yield_value=None) -> str:
    """Table cell for a metric. Valuation cells carry both the multiple and
    the yield, so the page can switch between them without recalculating."""
    cls = f"num{(' ' + extra_cls) if extra_cls else ''}"
    if config.METRICS[metric]["kind"] != "valuation":
        return f'<td class="{cls}" data-sort="{_sort_key(value)}">{_fmt_metric(metric, value)}</td>'
    y = _inverse(value) if yield_value is None else yield_value
    mult_txt, yld_txt = _fmt_metric(metric, value), _fmt_yield(y)
    sort_mult = _sort_key(value) if pd.notna(value) and value > 0 else ""
    return (f'<td class="{cls} vm" data-sort="{sort_mult}" data-sort-mult="{sort_mult}" '
            f'data-sort-yield="{_sort_key(y)}" data-mult="{_esc(mult_txt)}" '
            f'data-yield="{_esc(yld_txt)}">{mult_txt}</td>')


def _outlook():
    """Sector ranks under the assumed regime, with tie markers."""
    ranks = config.sector_ranks()
    counts = {}
    for rank, _ in ranks.values():
        counts[rank] = counts.get(rank, 0) + 1
    total = len(ranks)
    out = {}
    for key, (rank, score) in ranks.items():
        label = f"{'=' if counts[rank] > 1 else ''}{rank} of {total}"
        out[key] = {"rank": rank, "score": score, "label": label,
                    "reason": config.SECTOR_OUTLOOK[key][1]}
    return out


def _rank_cell(key: str, outlook: dict) -> str:
    o = outlook[key]
    tint = (f"background: rgba(var(--cheap-rgb), {o['score'] / 2 * 0.32:.3f})" if o["score"] > 0 else
            f"background: rgba(var(--dear-rgb), {-o['score'] / 2 * 0.32:.3f})" if o["score"] < 0 else "")
    title = f"Ranked {o['label']} sectors. {o['reason']}"
    return (f'<td class="num rank" data-sort="{o["score"]}" style="{tint}" '
            f'title="{_esc(title)}">{_fmt_outlook(o["score"])}</td>')


def _fmt_outlook(score: float) -> str:
    """+1.5, 0.0 or −1.5, with a true minus sign."""
    return "0.0" if score == 0 else f"{score:+.1f}".replace("-", "−")


def _fmt_score(value) -> str:
    return "–" if value is None or pd.isna(value) else f"{value:.0f}"


def _sort_key(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return f"{float(value):.6g}"


def _esc(text) -> str:
    return html.escape(str(text), quote=True)


def _score_cell(value) -> str:
    if value is None or pd.isna(value):
        return '<td class="num score" data-sort="">–</td>'
    return (f'<td class="num score" data-sort="{value:.3f}" '
            f'style="--s:{value / 100:.3f}">{value:.0f}</td>')


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _sector_table(key: str, table: pd.DataFrame) -> str:
    sector = config.SECTORS[key]
    metrics = list(sector["valuation"]) + list(sector["quality"])
    has_reg = sector.get("regression") and "reg_resid" in table.columns

    head = ['<th data-type="text">Company</th>', '<th class="num">Price (£)</th>', '<th class="num">Mkt cap (£bn)</th>']
    head += [_metric_th(m) for m in metrics]
    if has_reg:
        head.append('<th class="num" title="Multiple relative to the sector regression line. '
                    'Negative means cheaper than its fundamentals imply.">vs fitted</th>')
    head += [f'<th class="num">{label}</th>' for _, label in SCORE_COLUMNS]
    head.append('<th data-type="text">Flags</th>')

    body = []
    ordered = table.sort_values("composite", ascending=False, na_position="last")
    for ticker, row in ordered.iterrows():
        price_txt = "–" if pd.isna(row["price"]) else f"{row['price']:,.2f}"
        mcap_txt = "–" if pd.isna(row["market_cap"]) else f"{row['market_cap'] / 1e9:,.1f}"
        cells = [
            f'<td class="co" data-sort="{_esc(row["name"])}"><a href="#co-{_esc(ticker)}">'
            f'{_esc(row["name"])}</a><span class="tk">{_esc(ticker)}</span></td>',
            f'<td class="num" data-sort="{_sort_key(row["price"])}">{price_txt}</td>',
            f'<td class="num" data-sort="{_sort_key(row["market_cap"])}">{mcap_txt}</td>',
        ]
        for m in metrics:
            cells.append(_metric_td(m, row[m]))
        if has_reg:
            r = row["reg_resid"]
            r_txt = "–" if pd.isna(r) else f"{r:+.0%}"
            cells.append(f'<td class="num" data-sort="{_sort_key(r)}">{r_txt}</td>')
        for col, _ in SCORE_COLUMNS:
            cells.append(_score_cell(row[col]))
        flags = row["flags"] if isinstance(row["flags"], list) else []
        flag_html = "".join(f'<span class="flag{" warn" if "trap" in f or "Loss" in f else ""}">'
                            f'{_esc(f)}</span>' for f in flags)
        cells.append(f'<td class="flags" data-sort="{len(flags)}">{flag_html}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")

    return (f'<div class="table-wrap"><table class="sortable">'
            f'<thead><tr>{"".join(head)}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def _company_details(key: str, table: pd.DataFrame) -> str:
    sector = config.SECTORS[key]
    metrics = list(sector["valuation"]) + list(sector["quality"])
    medians = table[metrics].median()
    # Median of yields for valuation metrics, so loss-makers count correctly
    yield_medians = {m: table[m].map(_inverse).median()
                     for m in metrics if config.METRICS[m]["kind"] == "valuation"}
    parts = []
    ordered = table.sort_values("composite", ascending=False, na_position="last")
    for ticker, row in ordered.iterrows():
        rows = "".join(
            f'<tr>{_metric_th(m, scope="row")}{_metric_td(m, row[m])}'
            f'{_metric_td(m, medians[m], "muted", yield_medians.get(m))}</tr>'
            for m in metrics)
        period = "–" if pd.isna(row["period_end"]) else pd.Timestamp(row["period_end"]).strftime("%b %Y")
        hist_note = (f'{int(row["history_points"])} quarterly observations'
                     if pd.notna(row.get("history_points")) else "no history")
        parts.append(f"""
<details class="company" id="co-{_esc(ticker)}" data-sector="{key}" data-ticker="{_esc(ticker)}">
  <summary><span class="co-name">{_esc(row["name"])}</span>
    <span class="tk">{_esc(ticker)}</span>
    <span class="co-score">Composite {_fmt_score(row["composite"])}</span></summary>
  <div class="co-body">
    <div class="co-facts">
      <table class="mini"><thead><tr><th></th><th>Company</th><th>Sector median</th></tr></thead>
      <tbody>{rows}</tbody></table>
      <p class="muted small">Latest accounts used: {period}. History: {hist_note}.</p>
    </div>
    <div class="co-charts">
      <div class="chart-grid" data-role="history"></div>
      <div class="chart" data-role="dividend"></div>
    </div>
  </div>
</details>""")
    return "".join(parts)


def _sector_section(result: dict) -> str:
    key = result["key"]
    sector = config.SECTORS[key]
    table = result["table"]
    if table.empty:
        return (f'<section class="sector" id="s-{key}"><h2>{_esc(sector["name"])}</h2>'
                f'<p class="empty">No companies in this sector returned data. '
                f'Check the tickers in config.py.</p></section>')

    no_hist = table[table["history_value"].isna()]["name"].tolist()
    no_hist_note = (f'<p class="muted small">Not plotted (too little history): '
                    f'{_esc(", ".join(no_hist))}.</p>' if no_hist else "")
    reg_block = ('<figure class="panel"><figcaption>Multiple versus fundamentals'
                 '<span class="muted">. Points below the line are cheap given their fundamentals. '
                 'Always shown as a multiple, since the line is fitted to multiples.</span>'
                 '</figcaption><div class="chart" data-role="regression"></div></figure>'
                 if result["regression"] else "")

    return f"""
<section class="sector" id="s-{key}" data-sector="{key}">
  <header class="sector-head">
    <h2>{_esc(sector["name"])}</h2>
    <p class="notes">{_esc(sector["notes"])}</p>
    <p class="outlook">Outlook under {_esc(config.REGIME["name"].lower())}: score
      <strong>{_fmt_outlook(_outlook()[key]["score"])}</strong> (ranked {_outlook()[key]["label"]}).
      {_esc(_outlook()[key]["reason"])}</p>
  </header>
  <div class="sector-charts">
    <figure class="panel quadrant">
      <figcaption>Where each company sits: cheap against peers today (up) and against its own
        peer-relative history (right). Colour shows quality.</figcaption>
      <div class="chart tall" data-role="quadrant"></div>
      {no_hist_note}
    </figure>
    <figure class="panel"><figcaption>Sector percentiles<span class="muted">. Darker teal is cheaper or higher quality within the group, orange the opposite. Valuation metrics sit left of the divider, quality right. Hover over a cell for its percentile.</span></figcaption>
      <div class="chart" data-role="heatmap"></div></figure>
    {reg_block}
  </div>
  {_sector_table(key, table)}
  <div class="companies">{_company_details(key, table)}</div>
</section>"""


def _overview(results: list) -> str:
    frames = [r["table"] for r in results if not r["table"].empty]
    if not frames:
        return '<p class="empty">No data was returned for any sector.</p>'
    allrows = pd.concat(frames)
    top = allrows.sort_values("composite", ascending=False).head(config.SETTINGS["top_n_overall"])
    outlook = _outlook()
    rows = []
    for ticker, r in top.iterrows():
        flags = r["flags"] if isinstance(r["flags"], list) else []
        trap = any("trap" in f for f in flags)
        trap_html = '<span class="flag warn">Possible value trap</span>' if trap else ""
        rows.append(
            f'<tr><td class="co" data-sort="{_esc(r["name"])}"><a href="#co-{_esc(ticker)}">{_esc(r["name"])}</a>'
            f'<span class="tk">{_esc(ticker)}</span></td>'
            f'<td data-sort="{_esc(config.SECTORS[r["sector"]]["name"])}">'
            f'<a href="#s-{r["sector"]}">{_esc(config.SECTORS[r["sector"]]["name"])}</a></td>'
            + _rank_cell(r["sector"], outlook)
            + "".join(_score_cell(r[c]) for c, _ in SCORE_COLUMNS)
            + f'<td class="flags" data-sort="{int(trap)}">'
              f'{trap_html}</td></tr>')
    head = ('<th data-type="text">Company</th><th data-type="text">Sector</th>'
            '<th class="num" title="How the sector’s profitability is expected to fare under the '
            'assumed regime, from +2 (benefits strongly) to −2 (contracts sharply). '
            'Hover over a score for the reasoning.">Sector score</th>'
            + "".join(f'<th class="num">{label}</th>' for _, label in SCORE_COLUMNS) + '<th>Trap risk</th>')
    regime = config.REGIME
    return (f'<p class="regime">Assumed regime: <strong>{_esc(regime["name"])}</strong> '
            f'({_esc(regime["description"].lower())}). Sector score shows how each sector’s '
            f'profitability is expected to fare, from +2 (benefits strongly) to −2 (contracts sharply).</p>'
            f'<div class="table-wrap"><table class="sortable"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>'
            f'<p class="muted small">Stock scores are percentiles within each sector, so this list ranks '
            f'how strongly each company stands out from its own peers, not absolute cheapness '
            f'across sectors. The sector score is shown alongside but does not change any other score. '
            f'Hover over a sector score for the reasoning.</p>')


def _failures(failures: list) -> str:
    if not failures:
        return ""
    items = "".join(f'<li><strong>{_esc(f["ticker"])}</strong> {_esc(f["name"])} '
                    f'({_esc(config.SECTORS[f["sector"]]["name"])}): {_esc(f["reason"])}</li>'
                    for f in failures)
    return (f'<section class="failures"><h2>Tickers that failed to download</h2>'
            f'<p>These were skipped. Check whether the ticker has changed or the company '
            f'has delisted, then update config.py.</p><ul>{items}</ul></section>')


# ---------------------------------------------------------------------------
# Chart data
# ---------------------------------------------------------------------------

def _chart_payload(results: list) -> dict:
    payload = {"metrics": {k: {"label": v["label"], "kind": v["kind"],
                               "yield_label": v.get("yield_label", v["label"]),
                               "snapshot_only": v.get("snapshot_only", False)}
                           for k, v in config.METRICS.items()},
               "sectors": {}}
    for r in results:
        key, table = r["key"], r["table"]
        if table.empty:
            continue
        sector = config.SECTORS[key]
        val_m, qual_m = list(sector["valuation"]), list(sector["quality"])
        ordered = table.sort_values("composite", ascending=True, na_position="first")

        quadrant = [{"ticker": t, "name": row["name"], "x": row["history_value"], "y": row["peer_value"],
                     "q": row["quality"], "c": row["composite"]}
                    for t, row in table.iterrows() if pd.notna(row["history_value"]) and pd.notna(row["peer_value"])]

        heat_metrics = val_m + qual_m
        heatmap = {
            "x_mult": [config.METRICS[m]["label"] for m in heat_metrics],
            "x_yield": [config.METRICS[m].get("yield_label", config.METRICS[m]["label"]) for m in heat_metrics],
            "y": ordered["name"].tolist(),
            "z": [[row.get(f"pct_{m}") for m in heat_metrics] for _, row in ordered.iterrows()],
            "text_mult": [[_fmt_metric(m, row[m]) for m in heat_metrics] for _, row in ordered.iterrows()],
            "text_yield": [[_fmt_yield(_inverse(row[m])) if config.METRICS[m]["kind"] == "valuation"
                            else _fmt_metric(m, row[m]) for m in heat_metrics] for _, row in ordered.iterrows()],
            "split": len(val_m),
        }

        companies = {}
        for t in table.index:
            companies[t] = {"history": r["history"].get(t, {}), "dividend": r["div_bands"].get(t)}

        payload["sectors"][key] = {
            "quadrant": quadrant, "heatmap": heatmap, "regression": r["regression"],
            "valuation": val_m, "companies": companies,
        }
    return _clean(payload)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

CSS = r"""
:root {
  --bg: #0e1918; --surface: #152321; --ink: #e2ebe9; --muted: #92a5a1;
  --rule: #29403c; --cheap: #4fb5c1; --dear: #e29a55; --warn: #e07c7c;
  --cheap-rgb: 79,181,193; --dear-rgb: 226,154,85; --focus: #4fb5c1;
  color-scheme: dark;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.5 "IBM Plex Sans", "Segoe UI", system-ui, -apple-system, sans-serif;
  font-variant-numeric: tabular-nums;
}
a { color: var(--cheap); text-decoration: none; }
a:hover { text-decoration: underline; }
:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
h1, h2 { font-family: "Source Serif 4", Georgia, "Times New Roman", serif; font-weight: 600; }
.layout { display: grid; grid-template-columns: 220px minmax(0, 1fr); min-height: 100vh; }
nav.side {
  position: sticky; top: 0; height: 100vh; overflow-y: auto;
  padding: 28px 18px; border-right: 1px solid var(--rule); background: var(--surface);
}
nav.side .brand { font-family: "Source Serif 4", Georgia, serif; font-size: 18px; margin: 0 0 4px; }
nav.side .date { color: var(--muted); font-size: 13px; margin: 0 0 24px; }
.view-toggle { margin: 0 0 22px; }
.view-toggle p { font-size: 13px; color: var(--muted); margin: 0 0 6px; }
.view-toggle .seg { display: inline-flex; border: 1px solid var(--rule); border-radius: 4px; overflow: hidden; }
.view-toggle button {
  font: inherit; font-size: 13px; padding: 5px 12px; border: 0; cursor: pointer;
  background: var(--surface); color: var(--ink);
}
.view-toggle button + button { border-left: 1px solid var(--rule); }
.view-toggle button[aria-pressed="true"] { background: var(--ink); color: var(--surface); }
nav.side ol { list-style: none; padding: 0; margin: 0; }
nav.side li a {
  display: flex; justify-content: space-between; gap: 8px; padding: 6px 8px;
  border-radius: 4px; color: var(--ink); font-size: 14px;
}
nav.side li a:hover { background: var(--bg); text-decoration: none; }
nav.side li a span { color: var(--muted); }
main { padding: 36px clamp(16px, 4vw, 48px) 80px; max-width: 1400px; }
.intro h1 { font-size: 34px; line-height: 1.15; margin: 0 0 10px; max-width: 30ch; }
.intro p { max-width: 72ch; color: var(--muted); margin: 0 0 8px; }
.demo-banner {
  border-left: 4px solid var(--dear); background: var(--surface);
  padding: 10px 14px; margin: 18px 0; max-width: 72ch;
}
details.method { margin: 14px 0 0; max-width: 72ch; }
details.method summary { cursor: pointer; color: var(--cheap); }
details.method p, details.method li { color: var(--ink); }
.overview { margin: 36px 0 12px; }
.overview h2, .sector-head h2, .failures h2 { font-size: 26px; margin: 0 0 6px; }
section.sector { margin-top: 64px; padding-top: 28px; border-top: 2px solid var(--ink); }
.sector-head .notes { color: var(--muted); max-width: 72ch; margin: 0 0 10px; }
.sector-head .outlook { max-width: 72ch; margin: 0 0 20px; padding-left: 12px;
  border-left: 3px solid var(--rule); font-size: 14px; }
.overview .regime { max-width: 80ch; margin: 0 0 4px; }
td.rank { cursor: help; }
.sector-charts { display: grid; grid-template-columns: minmax(0, 1fr); gap: 18px; }
.sector-charts .quadrant { grid-column: 1 / -1; }
figure.panel { margin: 0; background: var(--surface); border: 1px solid var(--rule); padding: 14px 16px 8px; }
figure.panel figcaption { font-size: 14px; margin-bottom: 6px; max-width: 80ch; }
.chart { width: 100%; height: 340px; }
.chart.tall { height: 480px; }
.chart-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }
.chart-grid .chart { height: 220px; min-width: 0; overflow: hidden; }
.chart { min-width: 0; }
.table-wrap { overflow-x: auto; margin: 22px 0 8px; background: var(--surface); border: 1px solid var(--rule); }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; }
th, td { padding: 7px 10px; text-align: left; border-bottom: 1px solid var(--rule); white-space: nowrap; }
thead th { position: sticky; top: 0; background: var(--surface); font-weight: 600; cursor: pointer; user-select: none; }
thead th[aria-sort="ascending"]::after { content: " ▲"; font-size: 10px; }
thead th[aria-sort="descending"]::after { content: " ▼"; font-size: 10px; }
td.num, th.num { text-align: right; }
td.score { text-align: right; background: rgba(var(--cheap-rgb), calc(var(--s) * 0.32)); }
td.co a { font-weight: 500; }
.tk { color: var(--muted); font-size: 12px; margin-left: 6px; }
td.flags { white-space: normal; min-width: 180px; }
.flag { display: inline-block; font-size: 12px; padding: 1px 6px; margin: 1px 3px 1px 0;
  border: 1px solid var(--rule); border-radius: 3px; color: var(--muted); }
.flag.warn { border-color: var(--warn); color: var(--warn); }
.companies { margin-top: 18px; }
details.company { border-bottom: 1px solid var(--rule); }
details.company summary { cursor: pointer; padding: 10px 4px; display: flex; gap: 6px; align-items: baseline; }
details.company summary .co-name { font-weight: 500; }
details.company summary .co-score { margin-left: auto; color: var(--muted); font-size: 13px; }
.co-body { display: grid; grid-template-columns: 300px minmax(0, 1fr); gap: 20px; padding: 6px 4px 22px; }
table.mini th, table.mini td { padding: 4px 8px; font-size: 13px; }
table.mini thead th { cursor: default; position: static; }
.muted { color: var(--muted); }
.small { font-size: 13px; }
.empty { color: var(--muted); font-style: italic; }
.failures { margin-top: 64px; padding-top: 28px; border-top: 2px solid var(--ink); }
.failures li { margin-bottom: 4px; }
@media (max-width: 900px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
  nav.side { position: sticky; height: auto; z-index: 5; padding: 10px 14px; border-right: 0;
    border-bottom: 1px solid var(--rule); }
  nav.side .brand, nav.side .date, .view-toggle p { display: none; }
  .view-toggle { margin: 0 0 8px; }
  nav.side ol { display: flex; gap: 4px; overflow-x: auto; }
  nav.side li a { white-space: nowrap; }
  nav.side li a span { display: none; }
  .sector-charts { grid-template-columns: 1fr; }
  .co-body { grid-template-columns: 1fr; }
  .intro h1 { font-size: 28px; }
}
"""

JS = r"""
const DATA = JSON.parse(document.getElementById('chart-data').textContent);
let MODE = 'mult';  // 'mult' shows valuation as multiples, 'yield' as yields

function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

function baseLayout(extra) {
  const ink = css('--ink'), rule = css('--rule'), muted = css('--muted');
  const axis = { gridcolor: rule, zerolinecolor: rule, linecolor: rule, tickfont: { color: muted }, title: { font: { color: muted, size: 12 } } };
  const layout = {
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: '"IBM Plex Sans", system-ui, sans-serif', color: ink, size: 12 },
    margin: { l: 56, r: 16, t: 10, b: 44 },
    xaxis: Object.assign({}, axis), yaxis: Object.assign({}, axis),
    hoverlabel: { bgcolor: css('--surface'), bordercolor: rule,
                  font: { family: '"IBM Plex Sans", system-ui, sans-serif', color: ink } },
    modebar: { bgcolor: 'rgba(0,0,0,0)', color: muted, activecolor: ink },
    showlegend: false,
  };
  for (const [k, v] of Object.entries(extra || {})) {
    if ((k === 'xaxis' || k === 'yaxis') && typeof v === 'object') layout[k] = Object.assign(layout[k], v);
    else layout[k] = v;
  }
  return layout;
}
const CONFIG = { displaylogo: false, responsive: true, modeBarButtonsToRemove: ['lasso2d', 'select2d'] };

function diverging() {
  return [[0, css('--dear')], [0.5, css('--surface')], [1, css('--cheap')]];
}

function drawQuadrant(el, sector) {
  const pts = sector.quadrant;
  if (!pts.length) { el.innerHTML = '<p class="empty">Not enough history yet to place companies on this chart.</p>'; return; }
  const trace = {
    type: 'scatter', mode: 'markers+text',
    x: pts.map(p => p.x), y: pts.map(p => p.y),
    text: pts.map(p => p.ticker.replace('.L', '')), textposition: 'top center',
    textfont: { size: 11, color: css('--ink') },
    customdata: pts.map(p => [p.name, p.q == null ? '–' : Math.round(p.q), p.c == null ? '–' : Math.round(p.c)]),
    hovertemplate: '<b>%{customdata[0]}</b><br>Cheap vs peers: %{y:.0f}<br>Cheap vs own history: %{x:.0f}' +
                   '<br>Quality: %{customdata[1]}<br>Composite: %{customdata[2]}<extra></extra>',
    marker: {
      size: 14, line: { width: 1, color: css('--ink') },
      color: pts.map(p => p.q == null ? 50 : p.q), cmin: 0, cmax: 100,
      colorscale: [[0, css('--warn')], [0.5, css('--surface')], [1, css('--cheap')]],
      colorbar: { title: { text: 'Quality', side: 'right', font: { size: 12, color: css('--muted') } },
                  thickness: 10, len: 0.6, tickfont: { color: css('--muted') }, outlinewidth: 0 },
    },
  };
  const muted = css('--muted');
  const label = (x, y, t, anchor) => ({ x, y, xref: 'x', yref: 'y', text: t, showarrow: false,
      font: { size: 12, color: muted }, xanchor: anchor, yanchor: y > 50 ? 'top' : 'bottom' });
  const layout = baseLayout({
    xaxis: { range: [-4, 104], title: { text: 'Cheap versus own history →' }, zeroline: false, dtick: 25 },
    yaxis: { range: [-4, 108], title: { text: 'Cheap versus peers today →' }, zeroline: false, dtick: 25 },
    shapes: [
      { type: 'rect', x0: 50, x1: 104, y0: 50, y1: 108, fillcolor: `rgba(${css('--cheap-rgb')},0.08)`, line: { width: 0 }, layer: 'below' },
      { type: 'line', x0: 50, x1: 50, y0: -4, y1: 108, line: { color: css('--rule'), width: 1.5 } },
      { type: 'line', x0: -4, x1: 104, y0: 50, y1: 50, line: { color: css('--rule'), width: 1.5 } },
    ],
    annotations: [
      label(103, 107, 'Cheap on both', 'right'),
      label(-3, 107, 'Cheap vs peers, normal for itself', 'left'),
      label(103, -3, 'Cheap vs own history only', 'right'),
      label(-3, -3, 'Expensive on both', 'left'),
    ],
  });
  Plotly.react(el, [trace], layout, CONFIG);
}

// Break a column label onto short lines so it fits above a narrow column.
function wrapLabel(label, width) {
  const lines = [];
  let line = '';
  for (const word of label.split(' ')) {
    if (line && (line + ' ' + word).length > width) { lines.push(line); line = word; }
    else line = line ? line + ' ' + word : word;
  }
  if (line) lines.push(line);
  return lines.join('<br>');
}

function drawHeatmap(el, sector) {
  const h = sector.heatmap;
  const labels = (MODE === 'mult' ? h.x_mult : h.x_yield);
  // Narrower panels get narrower label lines
  const perColumn = el.clientWidth / Math.max(labels.length, 1);
  const width = Math.max(6, Math.floor(perColumn / 8));
  const wrapped = labels.map(l => wrapLabel(l, width));
  const labelLines = Math.max(...wrapped.map(l => l.split('<br>').length));
  const trace = {
    type: 'heatmap', x: wrapped, y: h.y, z: h.z,
    text: MODE === 'mult' ? h.text_mult : h.text_yield, zmin: 0, zmax: 100,
    colorscale: diverging(), xgap: 2, ygap: 2, showscale: false,
    texttemplate: '%{text}', textfont: { size: 11 },
    customdata: h.y.map(() => labels),
    hovertemplate: '%{y}<br>%{customdata}: %{text}<br>Percentile: %{z:.0f}<extra></extra>',
  };
  const layout = baseLayout({
    margin: { l: 10, r: 10, t: 10, b: 10 },
    xaxis: { side: 'top', showgrid: false, tickangle: 0, automargin: true, tickfont: { size: 11 } },
    yaxis: { showgrid: false, automargin: true },
    shapes: [{ type: 'line', xref: 'x', yref: 'paper', x0: h.split - 0.5, x1: h.split - 0.5, y0: 0, y1: 1,
               line: { color: css('--ink'), width: 2 } }],
  });
  el.style.height = Math.max(240, 40 + labelLines * 15 + h.y.length * 30) + 'px';
  Plotly.react(el, [trace], layout, CONFIG);
}

function drawRegression(el, sector) {
  const r = sector.regression;
  const xs = r.points.map(p => p.x);
  const lo = Math.min(...xs), hi = Math.max(...xs);
  const pct = DATA.metrics[r.x].label.includes('margin') || r.x === 'roe';
  const pts = {
    type: 'scatter', mode: 'markers+text', x: xs, y: r.points.map(p => p.y),
    text: r.points.map(p => p.ticker.replace('.L', '')), textposition: 'top center',
    textfont: { size: 11, color: css('--ink') },
    customdata: r.points.map(p => [p.name, p.resid == null ? '–' : (p.resid * 100).toFixed(0) + '%']),
    hovertemplate: '<b>%{customdata[0]}</b><br>' + DATA.metrics[r.x].label + ': %{x' + (pct ? ':.1%' : ':.2f') + '}' +
                   '<br>' + DATA.metrics[r.y].label + ': %{y:.2f}x<br>vs fitted: %{customdata[1]}<extra></extra>',
    marker: { size: 11, color: r.points.map(p => p.resid == null ? 0 : -p.resid), cmin: -0.5, cmax: 0.5,
              colorscale: diverging(), line: { width: 1, color: css('--ink') } },
  };
  const line = { type: 'scatter', mode: 'lines', x: [lo, hi], y: [r.intercept + r.slope * lo, r.intercept + r.slope * hi],
                 line: { color: css('--muted'), dash: 'dot', width: 1.5 }, hoverinfo: 'skip' };
  const layout = baseLayout({
    xaxis: { title: { text: DATA.metrics[r.x].label }, tickformat: pct ? '.0%' : '' },
    yaxis: { title: { text: DATA.metrics[r.y].label }, ticksuffix: 'x' },
  });
  Plotly.react(el, [line, pts], layout, CONFIG);
}

function historyLabel(metric) {
  const m = DATA.metrics[metric];
  if (m.kind !== 'valuation') return `${m.label} against sector median`;
  return MODE === 'mult' ? `${m.label} against sector median` : `${m.yield_label} (1 ÷ ${m.label}) against sector median`;
}
const toMultiple = arr => arr.map(v => (v == null || v <= 0) ? null : 1 / v);

function drawCompany(details) {
  const sector = DATA.sectors[details.dataset.sector];
  const co = sector.companies[details.dataset.ticker];
  if (!co) return;
  const grid = details.querySelector('[data-role="history"]');
  grid.innerHTML = '';
  // Create every chart box before drawing any, so each chart is sized to its
  // final grid cell rather than to the full row.
  const boxes = sector.valuation.map(() => {
    const el = document.createElement('div');
    el.className = 'chart';
    grid.appendChild(el);
    return el;
  });
  for (const [i, metric] of sector.valuation.entries()) {
    const h = co.history[metric];
    const el = boxes[i];
    const label = MODE === 'mult' ? DATA.metrics[metric].label : DATA.metrics[metric].yield_label;
    if (DATA.metrics[metric].snapshot_only) {
      el.innerHTML = `<p class="empty small">${label}: current value only, so there is no history to chart.</p>`;
      continue;
    }
    if (!h || !h.company.some(v => v != null)) {
      el.innerHTML = `<p class="empty small">${label}: no history available.</p>`;
      continue;
    }
    const mult = MODE === 'mult' && DATA.metrics[metric].kind === 'valuation';
    const fmt = mult ? ':.1f}x' : ':.1%}';
    const traces = [
      { type: 'scatter', mode: 'lines', name: 'Sector median', x: h.dates, y: mult ? toMultiple(h.median) : h.median,
        line: { color: css('--muted'), dash: 'dot', width: 1.5 }, hovertemplate: 'Sector median: %{y' + fmt + '<extra></extra>' },
      { type: 'scatter', mode: 'lines+markers', name: 'Company', x: h.dates, y: mult ? toMultiple(h.company) : h.company,
        line: { color: css('--cheap'), width: 2 }, marker: { size: 4 }, connectgaps: false,
        hovertemplate: '%{x|%b %Y}: %{y' + fmt + '<extra></extra>' },
    ];
    const layout = baseLayout({
      margin: { l: 48, r: 8, t: 30, b: 30 },
      title: { text: historyLabel(metric), font: { size: 12 }, x: 0, xanchor: 'left', y: 0.97 },
      yaxis: mult ? { tickformat: '.1f', ticksuffix: 'x' } : { tickformat: '.0%' }, showlegend: false,
    });
    Plotly.react(el, traces, layout, CONFIG);
  }
  const dEl = details.querySelector('[data-role="dividend"]');
  const d = co.dividend;
  if (!d) { dEl.style.height = 'auto'; dEl.innerHTML = '<p class="empty small">No dividend-yield history (no regular dividend, or under three years of data).</p>'; return; }
  const x0 = d.dates[0], x1 = d.dates[d.dates.length - 1];
  const band = (y0, y1, a) => ({ type: 'rect', xref: 'x', yref: 'y', x0, x1, y0, y1,
      fillcolor: `rgba(${css('--cheap-rgb')},${a})`, line: { width: 0 }, layer: 'below' });
  const layout = baseLayout({
    margin: { l: 48, r: 8, t: 30, b: 30 },
    title: { text: `Trailing dividend yield over ${d.years} years (shaded: 25th to 75th percentile)`, font: { size: 12 }, x: 0, xanchor: 'left', y: 0.97 },
    yaxis: { tickformat: '.1%' },
    shapes: [band(d.p25, d.p75, 0.12),
             { type: 'line', xref: 'x', yref: 'y', x0, x1, y0: d.p50, y1: d.p50, line: { color: css('--muted'), dash: 'dot', width: 1 } }],
  });
  Plotly.react(dEl, [{ type: 'scatter', mode: 'lines', x: d.dates, y: d.yield, line: { color: css('--cheap'), width: 1.8 },
                       hovertemplate: '%{x|%b %Y}: %{y:.2%}<extra></extra>' }], layout, CONFIG);
}

function drawSector(section) {
  const sector = DATA.sectors[section.dataset.sector];
  if (!sector) return;
  const q = section.querySelector('[data-role="quadrant"]'); if (q) drawQuadrant(q, sector);
  const h = section.querySelector('[data-role="heatmap"]'); if (h) drawHeatmap(h, sector);
  const r = section.querySelector('[data-role="regression"]'); if (r && sector.regression) drawRegression(r, sector);
  section.dataset.drawn = '1';
}

// Draw sector charts as they scroll into view, and company charts when opened.
const io = new IntersectionObserver(entries => {
  for (const e of entries) if (e.isIntersecting && !e.target.dataset.drawn) drawSector(e.target);
}, { rootMargin: '400px 0px' });
document.querySelectorAll('section.sector[data-sector]').forEach(s => io.observe(s));
document.querySelectorAll('details.company').forEach(d =>
  d.addEventListener('toggle', () => { if (d.open) drawCompany(d); }));

// Open a company's details when following a link to it.
function openFromHash() {
  const el = document.getElementById(decodeURIComponent(location.hash.slice(1)));
  if (el && el.tagName === 'DETAILS') { el.open = true; el.scrollIntoView(); }
}
window.addEventListener('hashchange', openFromHash);
openFromHash();

// Keep every drawn chart sized to its box when the layout changes.
const resizer = new ResizeObserver(entries => {
  for (const e of entries) if (e.target.data) Plotly.Plots.resize(e.target);
});
const observeCharts = () => document.querySelectorAll('.chart').forEach(el => {
  if (!el.dataset.observed) { el.dataset.observed = '1'; resizer.observe(el); }
});
new MutationObserver(observeCharts).observe(document.querySelector('main'), { childList: true, subtree: true });
observeCharts();

// Switch valuation metrics between multiples and yields.
function applyMode(mode) {
  MODE = mode;
  const key = mode === 'mult' ? 'Mult' : 'Yield';
  document.querySelectorAll('.view-toggle button').forEach(b =>
    b.setAttribute('aria-pressed', String(b.dataset.mode === mode)));
  document.querySelectorAll('[data-label-mult]').forEach(el => { el.textContent = el.dataset['label' + key]; });
  document.querySelectorAll('td.vm').forEach(td => {
    td.textContent = td.dataset[mode];
    td.dataset.sort = td.dataset['sort' + key];
  });
  // A column sorted under the old view is now in a different order
  document.querySelectorAll('th[aria-sort]').forEach(th => {
    if (th.hasAttribute('data-label-mult')) th.removeAttribute('aria-sort');
  });
  document.querySelectorAll('section.sector[data-drawn]').forEach(sec => {
    const h = sec.querySelector('[data-role="heatmap"]');
    if (h) drawHeatmap(h, DATA.sectors[sec.dataset.sector]);
  });
  document.querySelectorAll('details.company[open]').forEach(drawCompany);
}
document.querySelectorAll('.view-toggle button').forEach(b =>
  b.addEventListener('click', () => applyMode(b.dataset.mode)));

// Sortable tables: click a header to sort, click again to reverse.
document.querySelectorAll('table.sortable').forEach(table => {
  table.querySelectorAll('thead th').forEach((th, idx) => {
    th.tabIndex = 0;
    const sort = () => {
      const asc = th.getAttribute('aria-sort') === 'descending';
      table.querySelectorAll('thead th').forEach(h => h.removeAttribute('aria-sort'));
      th.setAttribute('aria-sort', asc ? 'ascending' : 'descending');
      const text = th.dataset.type === 'text';
      const body = table.tBodies[0];
      const rows = Array.from(body.rows);
      rows.sort((a, b) => {
        const va = a.cells[idx].dataset.sort ?? a.cells[idx].textContent;
        const vb = b.cells[idx].dataset.sort ?? b.cells[idx].textContent;
        if (va === '' && vb === '') return 0;
        if (va === '') return 1;
        if (vb === '') return -1;
        const cmp = text ? va.localeCompare(vb) : parseFloat(va) - parseFloat(vb);
        return asc ? cmp : -cmp;
      });
      rows.forEach(r => body.appendChild(r));
    };
    th.addEventListener('click', sort);
    th.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sort(); } });
  });
});
"""


def build_report(results: list, failures: list, generated: datetime, demo: bool = False) -> str:
    s = config.SETTINGS
    nav = "".join(
        f'<li><a href="#s-{r["key"]}">{_esc(config.SECTORS[r["key"]]["name"])}'
        f'<span>{len(r["table"])}</span></a></li>' for r in results)
    payload = json.dumps(_chart_payload(results), separators=(",", ":")).replace("</", "<\\/")
    weights = s["composite_weights"]
    demo_banner = ('<div class="demo-banner"><strong>Demo data.</strong> These figures are randomly '
                   'generated to show the report layout. Run without <code>--demo</code> for real data.</div>'
                   if demo else "")
    n_companies = sum(len(r["table"]) for r in results)

    return f"""<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>UK relative-value screen, {generated:%d %B %Y}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,600&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="layout">
<nav class="side" aria-label="Sectors">
  <p class="brand">UK value screen</p>
  <p class="date">{generated:%d %B %Y, %H:%M}</p>
  <div class="view-toggle" role="group" aria-label="Show valuation metrics as">
    <p>Show valuation as</p>
    <div class="seg">
      <button type="button" data-mode="mult" aria-pressed="true">Multiples</button>
      <button type="button" data-mode="yield" aria-pressed="false">Yields</button>
    </div>
  </div>
  <ol><li><a href="#overview">Strongest candidates</a></li>{nav}</ol>
</nav>
<main>
  <section class="intro">
    <h1>Which UK companies look cheap against their peers and their own history</h1>
    <p>{n_companies} companies across {len(results)} sectors, scored on data downloaded
       {generated:%d %B %Y}. Every score is a percentile within the company’s sector,
       from 0 (most expensive or weakest) to 100 (cheapest or strongest).</p>
    {demo_banner}
    <details class="method"><summary>How the scores are built</summary>
      <ul>
        <li><strong>Peers now:</strong> each valuation metric is converted to a yield (for example
            1 ÷ P/E), ranked within the sector, and combined using the weights in config.py.
            Converting to yields keeps loss-makers in the ranking as expensive, rather than producing
            meaningless negative multiples.</li>
        <li><strong>Own history:</strong> at each quarter end over the last {s["history_years"]} years,
            the company’s yield minus the sector median gives a spread. Today’s spread is ranked
            against the company’s past spreads. This removes market-wide re-rating. The fundamentals
            only change once a year, so treat this as indicative: the quarterly points are not
            independent.</li>
        <li><strong>Dividend yield history:</strong> today’s trailing 12-month yield ranked against
            up to {s["dividend_history_years"]} years of daily history, with special dividends excluded.</li>
        <li><strong>Quality:</strong> sector percentiles of profitability, cash and balance-sheet
            measures. For net debt/EBITDA and share count change, lower ranks higher.</li>
        <li><strong>Sector score:</strong> a judgement of how each sector’s profitability fares
            in the assumed macro regime, from +2 (benefits strongly) to −2 (contracts sharply),
            set in config.py. It is shown for context and does not feed into any other score.</li>
        <li><strong>Multiples or yields:</strong> the switch in the sidebar changes how valuation
            metrics are displayed (P/E of 10.0x or earnings yield of 10.0%). Scores are always
            calculated on yields, so they don’t change. Loss-makers show as n/m in multiple view
            and as a negative yield in yield view.</li>
        <li><strong>Forward P/E</strong> comes from Yahoo’s current analyst-estimate snapshot.
            It counts towards the peer score but has no history.</li>
        <li><strong>Composite:</strong> weighted {weights["peer_value"]:.0%} peers,
            {weights["history_value"]:.0%} own history, {weights["dividend_value"]:.0%} dividend history,
            {weights["quality"]:.0%} quality. Missing components are dropped and the weights rescaled.</li>
        <li>Accounts are assumed to become public {s["reporting_lag_days"]} days after the period end,
            so historical scores only use information available at the time.</li>
      </ul>
    </details>
  </section>
  <section class="overview" id="overview">
    <h2>Strongest candidates</h2>
    {_overview(results)}
  </section>
  {"".join(_sector_section(r) for r in results)}
  {_failures(failures)}
</main>
</div>
<script src="{PLOTLY_CDN}"></script>
<script type="application/json" id="chart-data">{payload}</script>
<script>{JS}</script>
</body>
</html>"""