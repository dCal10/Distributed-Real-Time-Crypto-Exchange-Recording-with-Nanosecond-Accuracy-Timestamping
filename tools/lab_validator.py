"""Lab-side sequence-gap validator for Parquet files written by collectors.

Reads Parquet output (from local data/ or from S3) for a single venue and
checks that the venue's sequence numbers are continuous. A detected gap
means the collector dropped a WS frame, which invalidates the order book
reconstruction starting at the gap.

Per-venue sequence-number rules (from each exchange's documented protocol):

  binance:   each @depth@100ms message carries U (first updateId) and u (last
             updateId). Consecutive frames for a symbol must satisfy
             this.U == prev.u + 1. Trade-stream messages are NOT sequence-
             checked (Binance doesn't promise gap-free trade delivery via WS).

  coinbase:  each Advanced Trade message carries top-level `sequence_num`,
             scoped per (product_id, channel). Must be monotonically
             increasing by 1.

Usage:
    python tools/lab_validator.py <venue> --data-dir <path>
    python tools/lab_validator.py <venue> --s3 <bucket>

Exit code: 0 if no gaps, 1 if any gaps detected, 2 on invocation error.

The script is standalone and intentionally not part of the production
pipeline. It's a debugging tool you run from anywhere.
"""

from __future__ import annotations

import argparse
import sys

import duckdb


def _binance_query(glob: str) -> str:
    return f"""
        WITH messages AS (
            SELECT
                symbol,
                t_exchange_ns,
                t_ptp_ns,
                CAST(json_extract_string(payload_json, '$.U') AS BIGINT) AS u_first,
                CAST(json_extract_string(payload_json, '$.u') AS BIGINT) AS u_last
            FROM read_parquet('{glob}', hive_partitioning=0)
            WHERE stream LIKE '%depth%'
        ),
        gaps AS (
            SELECT
                symbol,
                t_exchange_ns,
                t_ptp_ns,
                u_first,
                LAG(u_last) OVER w AS prev_u_last,
                u_first - LAG(u_last) OVER w - 1 AS gap_size,
                t_exchange_ns - LAG(t_exchange_ns) OVER w AS gap_duration_ns
            FROM messages
            WINDOW w AS (PARTITION BY symbol ORDER BY t_exchange_ns)
        )
        SELECT * FROM gaps WHERE gap_size > 0 ORDER BY symbol, t_exchange_ns
    """


def _coinbase_query(glob: str) -> str:
    return f"""
        WITH messages AS (
            SELECT
                symbol,
                stream,
                t_exchange_ns,
                t_ptp_ns,
                CAST(json_extract_string(payload_json, '$.sequence_num') AS BIGINT) AS seq
            FROM read_parquet('{glob}', hive_partitioning=0)
            WHERE json_extract_string(payload_json, '$.sequence_num') IS NOT NULL
        ),
        gaps AS (
            SELECT
                symbol,
                stream,
                t_exchange_ns,
                t_ptp_ns,
                seq,
                LAG(seq) OVER w AS prev_seq,
                seq - LAG(seq) OVER w - 1 AS gap_size,
                t_exchange_ns - LAG(t_exchange_ns) OVER w AS gap_duration_ns
            FROM messages
            WINDOW w AS (PARTITION BY symbol, stream ORDER BY t_exchange_ns)
        )
        SELECT * FROM gaps WHERE gap_size > 0 ORDER BY symbol, stream, t_exchange_ns
    """


VALIDATORS = {
    "binance": _binance_query,
    "coinbase": _coinbase_query,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Per-venue sequence-gap validator.")
    parser.add_argument("venue", choices=sorted(VALIDATORS.keys()))
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--data-dir", help="Local data dir; reads <dir>/<venue>/**/*.parquet")
    src.add_argument("--s3", help="S3 bucket; reads s3://<bucket>/<venue>/**/*.parquet")
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of gap rows to print (default 50)",
    )
    args = parser.parse_args()

    if args.data_dir:
        glob = f"{args.data_dir.rstrip('/')}/{args.venue}/**/*.parquet"
    else:
        glob = f"s3://{args.s3}/{args.venue}/**/*.parquet"

    con = duckdb.connect()
    if args.s3:
        con.execute("INSTALL httpfs; LOAD httpfs;")

    # Quick summary first so the operator knows scale
    summary = con.execute(
        f"SELECT COUNT(*) AS rows, MIN(t_exchange_ns) AS first_ns, MAX(t_exchange_ns) AS last_ns "
        f"FROM read_parquet('{glob}', hive_partitioning=0)"
    ).fetchone()
    total_rows, first_ns, last_ns = summary if summary else (0, None, None)
    span_s = (last_ns - first_ns) / 1e9 if first_ns and last_ns else 0
    print(f"venue={args.venue} source={glob}")
    print(f"  total records: {total_rows}")
    print(f"  span:          {span_s:.1f} s")

    query = VALIDATORS[args.venue](glob)
    gaps = con.execute(query).fetchall()

    if not gaps:
        print(f"  result:        OK (no sequence gaps detected)")
        return 0

    print(f"  result:        {len(gaps)} GAPS DETECTED")
    print()
    print("  showing first {n} gap(s):".format(n=min(args.limit, len(gaps))))
    header = ["symbol", "stream", "t_exchange_ns", "gap_size", "duration_ms"]
    if args.venue == "binance":
        # binance query has no stream column in gaps (only depth was filtered)
        header = ["symbol", "t_exchange_ns", "u_first", "prev_u_last", "gap_size", "duration_ms"]
    print("  " + " | ".join(f"{h:>16}" for h in header))
    print("  " + "-" * (len(header) * 19))
    for row in gaps[: args.limit]:
        if args.venue == "binance":
            symbol, t_ex, t_ptp, u_first, prev_u_last, gap_size, gap_dur_ns = row
            cells = [
                symbol,
                str(t_ex),
                str(u_first),
                str(prev_u_last),
                str(gap_size),
                f"{(gap_dur_ns or 0) / 1e6:.1f}",
            ]
        else:
            symbol, stream, t_ex, t_ptp, seq, prev_seq, gap_size, gap_dur_ns = row
            cells = [
                symbol,
                stream,
                str(t_ex),
                str(gap_size),
                f"{(gap_dur_ns or 0) / 1e6:.1f}",
            ]
        print("  " + " | ".join(f"{c:>16}" for c in cells))

    if len(gaps) > args.limit:
        print(f"  ... and {len(gaps) - args.limit} more")

    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(2)
