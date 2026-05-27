"""Produce the Tokyo baseline analysis report from accumulated Parquet data.

Runs against a local data/ directory (laptop test data) or, when invoked on
the Tokyo box, the production data/binance/ tree. Outputs:

  analysis/tokyo_baseline_report.md   - stats inline, Markdown
  analysis/charts/*.png               - matplotlib charts

Sections produced:
  1. delta_ns distribution per stream  (p25/p50/p75/p99 per btc/eth x depth/trade)
  2. hourly latency timeline           (median delta_ns + msg count per hour)
  3. (E - T) decomposition             (Binance @trade only; T from payload_json)
  4. message rate per stream           (messages/min over time)
  5. payload_json size distribution    (mean bytes/msg per stream)

Usage:
    python tools/produce_analysis_report.py --venue binance --data-dir data/

This becomes Section 5 of the final writeup once it has real Tokyo results.
The script is read-only against the data and writes only to analysis/.

matplotlib is already declared in requirements.txt (>=3.8); no new dep.
"""

from __future__ import annotations

import argparse
import statistics
from pathlib import Path

import duckdb

try:
    import matplotlib
    matplotlib.use("Agg")  # headless; safe on EC2 with no display
    import matplotlib.pyplot as plt
    _MPL = True
except ImportError:
    _MPL = False


def _glob(data_dir: str, venue: str) -> str:
    return f"{data_dir.rstrip('/')}/{venue}/**/*.parquet"


def _quantiles(con, glob: str) -> list[dict]:
    rows = con.execute(f"""
        SELECT
            stream,
            symbol,
            COUNT(*) AS n,
            APPROX_QUANTILE(delta_ns, 0.25) AS p25,
            APPROX_QUANTILE(delta_ns, 0.50) AS p50,
            APPROX_QUANTILE(delta_ns, 0.75) AS p75,
            APPROX_QUANTILE(delta_ns, 0.99) AS p99,
            MIN(delta_ns) AS min_d,
            MAX(delta_ns) AS max_d
        FROM read_parquet('{glob}', hive_partitioning=0)
        GROUP BY stream, symbol
        ORDER BY symbol, stream
    """).fetchall()
    return [
        {
            "stream": r[0], "symbol": r[1], "n": r[2],
            "p25_ms": (r[3] or 0) / 1e6, "p50_ms": (r[4] or 0) / 1e6,
            "p75_ms": (r[5] or 0) / 1e6, "p99_ms": (r[6] or 0) / 1e6,
            "min_ms": (r[7] or 0) / 1e6, "max_ms": (r[8] or 0) / 1e6,
        }
        for r in rows
    ]


def _hourly_timeline(con, glob: str) -> list[dict]:
    rows = con.execute(f"""
        SELECT
            CAST(t_exchange_ns / 3600000000000 AS BIGINT) AS hour_bucket,
            COUNT(*) AS n,
            APPROX_QUANTILE(delta_ns, 0.50) AS p50
        FROM read_parquet('{glob}', hive_partitioning=0)
        GROUP BY hour_bucket
        ORDER BY hour_bucket
    """).fetchall()
    return [{"hour": r[0], "n": r[1], "p50_ms": (r[2] or 0) / 1e6} for r in rows]


def _trade_decomposition(con, glob: str) -> list[dict]:
    rows = con.execute(f"""
        WITH m AS (
            SELECT
                symbol,
                t_exchange_ns,
                CAST(json_extract_string(payload_json, '$.T') AS BIGINT) * 1000000 AS t_match_ns
            FROM read_parquet('{glob}', hive_partitioning=0)
            WHERE stream LIKE '%trade'
              AND json_extract_string(payload_json, '$.T') IS NOT NULL
        )
        SELECT
            symbol,
            COUNT(*) AS n,
            APPROX_QUANTILE(t_exchange_ns - t_match_ns, 0.50) AS et_p50,
            APPROX_QUANTILE(t_exchange_ns - t_match_ns, 0.99) AS et_p99,
            AVG(t_exchange_ns - t_match_ns) AS et_mean
        FROM m
        GROUP BY symbol
        ORDER BY symbol
    """).fetchall()
    return [
        {
            "symbol": r[0], "n": r[1],
            "et_p50_ms": (r[2] or 0) / 1e6,
            "et_p99_ms": (r[3] or 0) / 1e6,
            "et_mean_ms": (r[4] or 0) / 1e6,
        }
        for r in rows
    ]


def _message_rate(con, glob: str) -> list[dict]:
    rows = con.execute(f"""
        SELECT
            stream,
            CAST(t_exchange_ns / 60000000000 AS BIGINT) AS minute_bucket,
            COUNT(*) AS n
        FROM read_parquet('{glob}', hive_partitioning=0)
        GROUP BY stream, minute_bucket
        ORDER BY stream, minute_bucket
    """).fetchall()
    return [{"stream": r[0], "minute": r[1], "n": r[2]} for r in rows]


def _payload_sizes(con, glob: str) -> list[dict]:
    rows = con.execute(f"""
        SELECT
            stream,
            COUNT(*) AS n,
            AVG(LENGTH(payload_json)) AS mean_bytes,
            APPROX_QUANTILE(LENGTH(payload_json), 0.50) AS p50_bytes,
            MAX(LENGTH(payload_json)) AS max_bytes
        FROM read_parquet('{glob}', hive_partitioning=0)
        GROUP BY stream
        ORDER BY stream
    """).fetchall()
    return [
        {
            "stream": r[0], "n": r[1],
            "mean_bytes": r[2] or 0, "p50_bytes": r[3] or 0, "max_bytes": r[4] or 0,
        }
        for r in rows
    ]


def _save_chart(fig, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return str(path)


def build(venue: str, data_dir: str, out_md: Path, charts_dir: Path) -> str:
    con = duckdb.connect()
    glob = _glob(data_dir, venue)

    # Fail soft if no data: produce a stub report so the writeup pipeline
    # still has a file to point at.
    try:
        total = con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{glob}', hive_partitioning=0)"
        ).fetchone()[0]
    except duckdb.IOException:
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(
            f"# Tokyo baseline report ({venue})\n\n"
            f"No Parquet data found at `{glob}`. Run this on the Tokyo box "
            f"(or point --data-dir at a populated tree) to generate real "
            f"results.\n"
        )
        return out_md.read_text()

    quant = _quantiles(con, glob)
    hourly = _hourly_timeline(con, glob)
    decomp = _trade_decomposition(con, glob)
    rates = _message_rate(con, glob)
    sizes = _payload_sizes(con, glob)

    lines: list[str] = []
    lines.append(f"# Tokyo baseline report ({venue})")
    lines.append("")
    lines.append(f"Total records: **{total}**  |  Source: `{glob}`")
    lines.append("")

    lines.append("## 1. delta_ns distribution per stream")
    lines.append("")
    lines.append("| symbol | stream | n | p25_ms | p50_ms | p75_ms | p99_ms | min_ms | max_ms |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for q in quant:
        lines.append(
            f"| {q['symbol']} | {q['stream']} | {q['n']} | {q['p25_ms']:.2f} | "
            f"{q['p50_ms']:.2f} | {q['p75_ms']:.2f} | {q['p99_ms']:.2f} | "
            f"{q['min_ms']:.2f} | {q['max_ms']:.2f} |"
        )
    lines.append("")

    lines.append("## 2. Hourly latency timeline")
    lines.append("")
    lines.append("| hour bucket | messages | median delta_ms |")
    lines.append("|---|---|---|")
    for h in hourly:
        lines.append(f"| {h['hour']} | {h['n']} | {h['p50_ms']:.2f} |")
    lines.append("")

    lines.append("## 3. (E - T) decomposition (Binance @trade)")
    lines.append("")
    if decomp:
        lines.append("| symbol | n | (E-T) p50_ms | (E-T) p99_ms | (E-T) mean_ms |")
        lines.append("|---|---|---|---|---|")
        for d in decomp:
            lines.append(
                f"| {d['symbol']} | {d['n']} | {d['et_p50_ms']:.3f} | "
                f"{d['et_p99_ms']:.3f} | {d['et_mean_ms']:.3f} |"
            )
        lines.append("")
        lines.append(
            "_(E - T) is the gap between Binance's WS-server event time (E) "
            "and the matching-engine trade time (T): the Binance-internal "
            "matching-engine-to-WS-server segment._"
        )
    else:
        lines.append("_No @trade records with a T field found._")
    lines.append("")

    lines.append("## 4. Message rate per stream")
    lines.append("")
    rate_by_stream: dict[str, list[int]] = {}
    for r in rates:
        rate_by_stream.setdefault(r["stream"], []).append(r["n"])
    lines.append("| stream | minutes observed | mean msgs/min | peak msgs/min |")
    lines.append("|---|---|---|---|")
    for stream, counts in sorted(rate_by_stream.items()):
        mean_rate = statistics.mean(counts) if counts else 0
        lines.append(
            f"| {stream} | {len(counts)} | {mean_rate:.1f} | {max(counts) if counts else 0} |"
        )
    lines.append("")

    lines.append("## 5. payload_json size distribution")
    lines.append("")
    lines.append("| stream | n | mean_bytes | p50_bytes | max_bytes |")
    lines.append("|---|---|---|---|---|")
    for s in sizes:
        lines.append(
            f"| {s['stream']} | {s['n']} | {s['mean_bytes']:.0f} | "
            f"{s['p50_bytes']:.0f} | {s['max_bytes']:.0f} |"
        )
    lines.append("")

    # Charts
    if _MPL:
        chart_paths = []
        # delta_ns p50 bar per stream
        if quant:
            fig, ax = plt.subplots(figsize=(9, 4))
            labels = [f"{q['symbol']}\n{q['stream']}" for q in quant]
            ax.bar(labels, [q["p50_ms"] for q in quant])
            ax.set_ylabel("median delta_ns (ms)")
            ax.set_title(f"{venue}: median latency per stream")
            ax.tick_params(axis="x", labelsize=7)
            chart_paths.append(_save_chart(fig, charts_dir / "delta_p50_per_stream.png"))
        # hourly timeline
        if hourly:
            fig, ax = plt.subplots(figsize=(9, 4))
            ax.plot([h["hour"] for h in hourly], [h["p50_ms"] for h in hourly], marker="o")
            ax.set_xlabel("hour bucket (epoch hours)")
            ax.set_ylabel("median delta_ns (ms)")
            ax.set_title(f"{venue}: latency drift over time")
            chart_paths.append(_save_chart(fig, charts_dir / "hourly_latency.png"))
        lines.append("## Charts")
        lines.append("")
        for cp in chart_paths:
            rel = Path(cp).relative_to(out_md.parent)
            lines.append(f"![{rel}]({rel})")
        lines.append("")
    else:
        lines.append("## Charts")
        lines.append("")
        lines.append("_matplotlib not importable; charts skipped. Stats above are complete._")
        lines.append("")

    report = "\n".join(lines)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Tokyo baseline analysis report generator.")
    parser.add_argument("--venue", default="binance")
    parser.add_argument("--data-dir", default="data/")
    parser.add_argument("--out", default="analysis/tokyo_baseline_report.md")
    parser.add_argument("--charts-dir", default="analysis/charts")
    args = parser.parse_args()

    out_md = Path(args.out)
    charts_dir = Path(args.charts_dir)
    report = build(args.venue, args.data_dir, out_md, charts_dir)
    print(report)
    print(f"\nwritten: {out_md}")
    if _MPL:
        print(f"charts:  {charts_dir}/")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
