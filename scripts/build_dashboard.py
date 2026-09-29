"""Dựng dashboard runtime 6 panel từ data/logs.jsonl theo contract config/dashboard.yaml.

    python scripts/build_dashboard.py                 # -> data/dashboard.html
    python scripts/build_dashboard.py --out x.html

Mỗi panel tính đúng aggregation trong contract, hiển thị đơn vị, time range và
threshold line. Trang tự refresh theo `refresh_seconds` (chạy lại script để có số mới).
"""
from __future__ import annotations

import argparse
import html
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile (cùng cách với app/metrics.py)."""
    if not values:
        return None
    items = sorted(values)
    idx = max(0, min(len(items) - 1, math.ceil(p / 100 * len(items)) - 1))
    return float(items[idx])


def load_events(path: Path, minutes: int) -> tuple[list[dict], datetime, datetime]:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "ts" in event:
            event["_ts"] = _parse_ts(event["ts"])
            events.append(event)
    end = max((e["_ts"] for e in events), default=datetime.now(timezone.utc))
    start = end - timedelta(minutes=minutes)
    return [e for e in events if e["_ts"] >= start], start, end


def minute_buckets(start: datetime, end: datetime) -> list[datetime]:
    cur = start.replace(second=0, microsecond=0)
    out = []
    while cur <= end:
        out.append(cur)
        cur += timedelta(minutes=1)
    return out


def by_minute(events: list[dict], event_name: str) -> dict[datetime, list[dict]]:
    groups: dict[datetime, list[dict]] = defaultdict(list)
    for e in events:
        if e.get("event") == event_name:
            groups[e["_ts"].replace(second=0, microsecond=0)].append(e)
    return groups


def compute(events: list[dict], start: datetime, end: datetime) -> dict:
    minutes = minute_buckets(start, end)
    labels = [m.strftime("%H:%M") for m in minutes]
    sent = [e for e in events if e.get("event") == "response_sent"]
    received = [e for e in events if e.get("event") == "request_received"]
    failed = [e for e in events if e.get("event") == "request_failed"]
    sent_m, recv_m, fail_m = by_minute(events, "response_sent"), by_minute(events, "request_received"), by_minute(events, "request_failed")

    def series(fn, groups):
        return [fn(groups.get(m, [])) for m in minutes]

    lat = lambda rows, p: percentile([r["latency_ms"] for r in rows], p)
    tool_rows = lambda rows: [r for r in rows if r.get("tool_success") is not None]
    tool_ok_pct = lambda rows: (100 * sum(r["tool_success"] is True for r in rows) / len(rows)) if rows else None

    per_min_tool = [tool_ok_pct(tool_rows(sent_m.get(m, []) + fail_m.get(m, []))) for m in minutes]
    per_min_err = [
        (100 * len(fail_m.get(m, [])) / len(recv_m.get(m, []))) if recv_m.get(m) else None for m in minutes
    ]
    cost_per_min = series(lambda rows: round(sum(r["cost_usd"] for r in rows), 6), sent_m)
    cumulative, running = [], 0.0
    for c in cost_per_min:
        running += c
        cumulative.append(round(running, 6))
    error_breakdown: dict[str, int] = defaultdict(int)
    for f in failed:
        error_breakdown[f.get("error_type") or "unknown"] += 1

    return {
        "labels": labels,
        "latency": {
            "p50": series(lambda r: lat(r, 50), sent_m),
            "p95": series(lambda r: lat(r, 95), sent_m),
            "p99": series(lambda r: lat(r, 99), sent_m),
            "ttft_p95": series(lambda r: percentile([x["ttft_ms"] for x in r], 95), sent_m),
            "summary": {
                "P50": lat(sent, 50), "P95": lat(sent, 95), "P99": lat(sent, 99),
                "TTFT P95": percentile([r["ttft_ms"] for r in sent], 95),
            },
        },
        "traffic": {
            "rpm": series(len, recv_m),
            "summary": {"count": len(received), "rate_per_minute (avg)": round(len(received) / max(1, len([m for m in minutes if recv_m.get(m)])), 1)},
        },
        "errors": {
            "error_rate": per_min_err,
            "tool_success": per_min_tool,
            "summary": {
                "error_rate_pct": round(100 * len(failed) / len(received), 2) if received else 0,
                "retrieval_success_pct": round(tool_ok_pct(tool_rows(sent + failed)) or 0, 2),
                "by error_type": dict(error_breakdown) or {"(none)": 0},
            },
        },
        "cost": {
            "per_minute": cost_per_min,
            "cumulative": cumulative,
            "summary": {"total_usd": round(sum(r["cost_usd"] for r in sent), 4)},
        },
        "tokens": {
            "in": series(lambda r: sum(x["tokens_in"] for x in r), sent_m),
            "out": series(lambda r: sum(x["tokens_out"] for x in r), sent_m),
            "summary": {"tokens_in": sum(r["tokens_in"] for r in sent), "tokens_out": sum(r["tokens_out"] for r in sent)},
        },
        "quality": {
            "mean": series(lambda r: round(mean(x["quality_score"] for x in r), 3) if r else None, sent_m),
            "summary": {"mean": round(mean(r["quality_score"] for r in sent), 3) if sent else None},
        },
    }


PAGE = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="{refresh}">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#0f1419;color:#e6e6e6}}
 header{{padding:14px 22px;border-bottom:1px solid #2a3139;display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px}}
 h1{{font-size:18px;margin:0}} .meta{{font-size:12px;color:#9aa4ad}}
 .grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;padding:14px 22px}}
 .panel{{background:#161c22;border:1px solid #2a3139;border-radius:10px;padding:12px}}
 .panel h2{{font-size:14px;margin:0 0 4px}} .unit{{font-size:11px;color:#9aa4ad}}
 .stats{{font-size:12px;color:#c9d1d9;margin:6px 0;min-height:32px}} .stats b{{color:#fff}}
 .th{{font-size:11px;color:#ff9f43}} canvas{{max-height:190px}}
</style></head><body>
<header><h1>{title}</h1>
<div class="meta">Source: <code>data/logs.jsonl</code> · Time range: last {minutes} min ({start} → {end} UTC) · Auto-refresh {refresh}s · Generated {generated} UTC</div></header>
<div class="grid">{panels}</div>
<script>
const D = {data};
const TH = {thresholds};
const opts = (unit, extra={{}}) => ({{responsive:true, animation:false, spanGaps:true,
  plugins:{{legend:{{labels:{{color:'#c9d1d9',boxWidth:10,font:{{size:10}}}}}}}},
  scales:{{x:{{ticks:{{color:'#9aa4ad',maxTicksLimit:8}},grid:{{color:'#222a31'}}}},
          y:{{title:{{display:true,text:unit,color:'#9aa4ad'}},ticks:{{color:'#9aa4ad'}},grid:{{color:'#222a31'}},...extra}}}}}});
const line = (label, data, color, dash) => ({{label, data, borderColor:color, backgroundColor:color, borderWidth:dash?1.5:2, borderDash:dash||[], pointRadius:dash?0:2, tension:.2}});
const thr = (id, color='#ff9f43') => ({{...line('threshold '+TH[id].operator+' '+TH[id].value, D.labels.map(_=>TH[id].value), color, [6,4]), type:'line'}});
const mk = (id, type, datasets, unit, extra) => new Chart(document.getElementById(id), {{type, data:{{labels:D.labels, datasets}}, options:opts(unit, extra)}});
mk('latency','line',[line('P50',D.latency.p50,'#4cc9f0'),line('P95',D.latency.p95,'#f72585'),line('P99',D.latency.p99,'#b5179e'),line('TTFT P95',D.latency.ttft_p95,'#80ed99'),thr('latency')],'ms');
mk('traffic','bar',[{{label:'requests / min',data:D.traffic.rpm,backgroundColor:'#4895ef'}},thr('traffic')],'requests_per_minute');
mk('errors','line',[line('error rate %',D.errors.error_rate,'#ef476f'),line('retrieval success %',D.errors.tool_success,'#06d6a0'),thr('errors')],'percent',{{min:0,max:100}});
mk('cost','bar',[{{label:'cost / min (USD)',data:D.cost.per_minute,backgroundColor:'#ffd166'}},{{...line('cumulative total',D.cost.cumulative,'#f8961e'),type:'line'}},thr('cost')],'usd');
mk('tokens','bar',[{{label:'tokens_in',data:D.tokens.in,backgroundColor:'#4cc9f0'}},{{label:'tokens_out',data:D.tokens.out,backgroundColor:'#7209b7'}}],'tokens',{{stacked:true}});
mk('quality','line',[line('mean quality_score',D.quality.mean,'#90be6d'),thr('quality')],'score_0_to_1',{{min:0,max:1}});
</script></body></html>"""


def fmt(value) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{k}={v}" for k, v in value.items())
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return "—" if value is None else f"{value:,}" if isinstance(value, int) else str(value)


def render(config: dict, data: dict, start: datetime, end: datetime) -> str:
    dash = config["dashboard"]
    panel_html, thresholds = [], {}
    for panel in dash["panels"]:
        pid = panel["id"]
        th = panel["threshold"]
        thresholds[pid] = {"operator": "≤" if th["operator"] == "lte" else "≥", "value": th["value"]}
        stats = " · ".join(f"{k}: <b>{html.escape(fmt(v))}</b>" for k, v in data[pid]["summary"].items())
        panel_html.append(
            f'<div class="panel"><h2>{html.escape(panel["title"])}</h2>'
            f'<div class="unit">unit: {html.escape(panel["unit"])} · aggregations: {", ".join(panel["aggregations"])}</div>'
            f'<div class="stats">{stats}</div>'
            f'<div class="th">threshold: {th["aggregation"]} {thresholds[pid]["operator"]} {th["value"]} {html.escape(panel["unit"])}</div>'
            f'<canvas id="{pid}"></canvas></div>'
        )
    return PAGE.format(
        title=html.escape(dash["title"]), refresh=dash["refresh_seconds"], minutes=dash["time_range_minutes"],
        start=start.strftime("%Y-%m-%d %H:%M"), end=end.strftime("%H:%M"),
        generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        panels="".join(panel_html), data=json.dumps(data), thresholds=json.dumps(thresholds),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "config/dashboard.yaml"))
    parser.add_argument("--logs", default=str(ROOT / "data/logs.jsonl"))
    parser.add_argument("--out", default=str(ROOT / "data/dashboard.html"))
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    events, start, end = load_events(Path(args.logs), config["dashboard"]["time_range_minutes"])
    data = compute(events, start, end)
    Path(args.out).write_text(render(config, data, start, end), encoding="utf-8")
    print(f"Dashboard -> {args.out} ({len(events)} events, {start:%H:%M}–{end:%H:%M} UTC)")
    for pid in ("latency", "traffic", "errors", "cost", "tokens", "quality"):
        print(f"  {pid:8} {fmt(data[pid]['summary'])}")


if __name__ == "__main__":
    main()
