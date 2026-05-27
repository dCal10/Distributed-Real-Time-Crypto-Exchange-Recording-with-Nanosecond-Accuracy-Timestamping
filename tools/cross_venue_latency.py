"""Cross-venue latency analysis (skeleton).

Notebook-style script. Each `# %%` block is an executable cell in VSCode's
Python interactive mode (or Jupyter via jupytext). Designed to run end to end
from the CLI too:

    python tools/cross_venue_latency.py --data-dir data/ --venues binance coinbase okx

What this script does:

  1. Per-venue latency distributions. For each venue+stream, computes p50/p95/p99
     of (t_ptp_ns - t_exchange_ns). For trade streams, ALSO computes
     (t_exchange_ns - t_match_ns) where t_match comes from the per-event T field
     inside payload_json. This decomposes total latency into "matching engine
     to WS server flush" (E - T) and "WS server flush to collector" (t_ptp - E).

  2. Cross-venue arrival ordering (skeleton). For overlapping symbols, takes the
     trade events that fall in a sliding time window across venues and computes
     which venue's stamp arrived first at the collector. SKELETON: the symbol-
     matching heuristic is naive (price+size+window); production-grade matching
     requires more careful trade-id correlation when available.

  3. Output: a Markdown report at tools/output/cross_venue_report.md and text
     histograms in stdout (no matplotlib dep required).

This is a skeleton meant to be filled in once multi-region data is flowing.
Per-venue stats work today against Tokyo's Binance capture; cross-venue
sections wait on Coinbase/OKX deployments.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

import duckdb

# Map any venue -> name of its trade-stream identifier in the `stream` column.
# (Used to identify which records have a per-event T field worth extracting.)
TRADE_STREAM_NAMES = {
    "binance": "btcusdt@trade",   # any symbol's @trade; match by suffix below
    "coinbase": "market_trades",
    "okx": "trades",
}


# %% Cell 1: load + summarize each venue ------------------------------------------------

def per_venue_summary(con: duckdb.DuckDBPyConnection, venue: str, glob: str) -> dict:
    """Return a dict of per-stream latency stats for one venue.

    Stats include count, mean, median, p95, p99 of delta_ns (t_ptp - t_exchange).
    For trade streams, also includes the matching-engine-to-WS-flush delta if
    payload_json carries a T (Binance) or `time` (Coinbase) per-event field.
    """
    rows = con.execute(f"""
        SELECT
            stream,
            COUNT(*) AS n,
            AVG(delta_ns) AS mean_delta,
            APPROX_QUANTILE(delta_ns, 0.50) AS p50,
            APPROX_QUANTILE(delta_ns, 0.95) AS p95,
            APPROX_QUANTILE(delta_ns, 0.99) AS p99,
            MIN(delta_ns) AS min_delta,
            MAX(delta_ns) AS max_delta
        FROM read_parquet('{glob}', hive_partitioning=0)
        GROUP BY stream
        ORDER BY stream
    """).fetchall()
    return {
        "venue": venue,
        "streams": [
            {
                "stream": r[0],
                "n": r[1],
                "mean_ms": (r[2] or 0) / 1e6,
                "p50_ms": (r[3] or 0) / 1e6,
                "p95_ms": (r[4] or 0) / 1e6,
                "p99_ms": (r[5] or 0) / 1e6,
                "min_ms": (r[6] or 0) / 1e6,
                "max_ms": (r[7] or 0) / 1e6,
            }
            for r in rows
        ],
    }


# %% Cell 2: matching-engine vs WS-server decomposition (trade streams only) -----------

def trade_decomposition(con: duckdb.DuckDBPyConnection, venue: str, glob: str) -> list[dict]:
    """For trade-stream records that carry a per-event matching engine timestamp,
    compute (E - T) (matching engine to WS server) and (t_ptp - E) (WS server to
    collector). Returns one summary dict per (venue, symbol).
    """
    # Binance @trade has top-level T in ms inside payload_json.data; our
    # collector inlines data as payload_json, so $.T is the right path.
    # Coinbase market_trades has events[0].trades[0].time as ISO string;
    # extracting that via SQL is brittle, so for now we only do Binance.
    if venue != "binance":
        return []
    rows = con.execute(f"""
        WITH messages AS (
            SELECT
                symbol,
                t_exchange_ns,
                t_ptp_ns,
                CAST(json_extract_string(payload_json, '$.T') AS BIGINT) AS t_match_ms
            FROM read_parquet('{glob}', hive_partitioning=0)
            WHERE stream LIKE '%trade'
              AND json_extract_string(payload_json, '$.T') IS NOT NULL
        )
        SELECT
            symbol,
            COUNT(*) AS n,
            AVG(t_exchange_ns - t_match_ms * 1000000) AS engine_to_ws_mean,
            APPROX_QUANTILE(t_exchange_ns - t_match_ms * 1000000, 0.50) AS engine_to_ws_p50,
            APPROX_QUANTILE(t_exchange_ns - t_match_ms * 1000000, 0.99) AS engine_to_ws_p99,
            AVG(t_ptp_ns - t_exchange_ns) AS ws_to_collector_mean,
            APPROX_QUANTILE(t_ptp_ns - t_exchange_ns, 0.50) AS ws_to_collector_p50,
            APPROX_QUANTILE(t_ptp_ns - t_exchange_ns, 0.99) AS ws_to_collector_p99
        FROM messages
        GROUP BY symbol
        ORDER BY symbol
    """).fetchall()
    return [
        {
            "venue": venue,
            "symbol": r[0],
            "n": r[1],
            "engine_to_ws_mean_ms": (r[2] or 0) / 1e6,
            "engine_to_ws_p50_ms": (r[3] or 0) / 1e6,
            "engine_to_ws_p99_ms": (r[4] or 0) / 1e6,
            "ws_to_collector_mean_ms": (r[5] or 0) / 1e6,
            "ws_to_collector_p50_ms": (r[6] or 0) / 1e6,
            "ws_to_collector_p99_ms": (r[7] or 0) / 1e6,
        }
        for r in rows
    ]


# %% Cell 3: cross-venue arrival ordering (SKELETON) -----------------------------------

def cross_venue_arrival_skeleton(globs_by_venue: dict[str, str]) -> dict:
    """TODO: implement cross-venue arrival ordering.

    Pseudocode:
        1. For each venue with a trade stream, extract (t_ptp_ns, price, size, side)
           for symbol "BTC" (mapped per venue: BTCUSDT @ binance, BTC-USD @
           coinbase, BTC-USDT @ okx).
        2. Sort all events globally by t_ptp_ns.
        3. For each event, look back/forward W microseconds for matching events
           in other venues (matching on price within tolerance, same side).
        4. For matched groups, report which venue's t_ptp_ns is minimum.

    The hard part is the matching heuristic. Trade IDs are venue-local; price+size
    can collide; the time window W has to be wide enough to capture real cross-
    venue arbitrage but narrow enough not to match unrelated trades. Defer to
    multi-region data so we can tune W empirically.
    """
    return {
        "status": "SKELETON; implement once multi-region data lands",
        "venues_seen": list(globs_by_venue.keys()),
    }


# %% Cell 4: text histogram helper ------------------------------------------------------

def text_histogram(values_ms: list[float], bins: int = 20, width: int = 50) -> str:
    """Render a stdout-friendly histogram. No matplotlib dep."""
    if not values_ms:
        return "(no data)"
    lo, hi = min(values_ms), max(values_ms)
    if lo == hi:
        return f"all values = {lo:.2f} ms ({len(values_ms)} samples)"
    bin_w = (hi - lo) / bins
    counts = [0] * bins
    for v in values_ms:
        idx = min(int((v - lo) / bin_w), bins - 1)
        counts[idx] += 1
    max_count = max(counts)
    lines = []
    for i, c in enumerate(counts):
        bin_lo = lo + i * bin_w
        bar = "#" * int(width * c / max_count) if max_count else ""
        lines.append(f"  {bin_lo:>8.2f}ms |{bar:<{width}}| {c}")
    return "\n".join(lines)


# %% Cell 5: end-to-end driver ----------------------------------------------------------

def build_report(venues: list[str], data_dir: str, output_path: Path) -> str:
    con = duckdb.connect()
    globs_by_venue = {v: f"{data_dir.rstrip('/')}/{v}/**/*.parquet" for v in venues}

    md_lines = ["# Cross-venue latency report", "", "## Per-venue summaries", ""]
    for venue in venues:
        glob = globs_by_venue[venue]
        try:
            summary = per_venue_summary(con, venue, glob)
        except duckdb.IOException:
            md_lines.append(f"### {venue}\n\n(no data at `{glob}`)\n")
            continue
        md_lines.append(f"### {venue}")
        md_lines.append("")
        md_lines.append("| stream | n | mean_ms | p50_ms | p95_ms | p99_ms |")
        md_lines.append("|---|---|---|---|---|---|")
        for s in summary["streams"]:
            md_lines.append(
                f"| {s['stream']} | {s['n']} | {s['mean_ms']:.2f} | "
                f"{s['p50_ms']:.2f} | {s['p95_ms']:.2f} | {s['p99_ms']:.2f} |"
            )
        md_lines.append("")

    md_lines.append("## Trade decomposition (Binance only for now)")
    md_lines.append("")
    for venue in venues:
        decomp = trade_decomposition(con, venue, globs_by_venue[venue])
        for d in decomp:
            md_lines.append(
                f"- **{venue}/{d['symbol']}** (n={d['n']}): "
                f"engine→WS p50={d['engine_to_ws_p50_ms']:.2f}ms "
                f"p99={d['engine_to_ws_p99_ms']:.2f}ms; "
                f"WS→collector p50={d['ws_to_collector_p50_ms']:.2f}ms "
                f"p99={d['ws_to_collector_p99_ms']:.2f}ms"
            )
    md_lines.append("")

    md_lines.append("## Cross-venue arrival ordering")
    md_lines.append("")
    md_lines.append(json.dumps(cross_venue_arrival_skeleton(globs_by_venue), indent=2))
    md_lines.append("")

    report = "\n".join(md_lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-venue latency analysis skeleton.")
    parser.add_argument("--data-dir", default="data/", help="Local Parquet root (default: data/)")
    parser.add_argument(
        "--venues",
        nargs="+",
        default=["binance"],
        help="Venues to include (e.g. binance coinbase okx)",
    )
    parser.add_argument(
        "--output",
        default="tools/output/cross_venue_report.md",
        help="Markdown report output path",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    report = build_report(args.venues, args.data_dir, output_path)
    print(report)
    print(f"\nwritten: {output_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
