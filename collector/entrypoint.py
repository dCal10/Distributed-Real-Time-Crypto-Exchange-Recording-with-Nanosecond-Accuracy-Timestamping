"""CLI entrypoint: python -m collector.entrypoint --venue <name>.

Resolves the timestamp source and sink from RECORDING_CONFIG (local|aws), then
runs the named venue's collector. One process per venue per EC2 instance.
"""

from __future__ import annotations

import argparse
import asyncio
import os

from collector.config_loader import load_config
from collector.exchanges import EXCHANGES
from collector.timestamp.base import TimestampSource
from collector.timestamp.clock_gettime_source import ClockGettimeSource
from collector.timestamp.nic_hw_source import NICHwTimestampSource
from collector.timestamp.ptp_source import PTPClockGettimeSource
from sinks.base_sink import RecordSink
from sinks.local_parquet_sink import LocalParquetSink
from sinks.s3_parquet_sink import S3ParquetSink


_TIMESTAMP_SOURCES: dict[str, type[TimestampSource]] = {
    "clock_gettime": ClockGettimeSource,
    "ptp_clock_gettime": PTPClockGettimeSource,
    "nic_hw": NICHwTimestampSource,
}


def _build_timestamp_source(cfg: dict) -> TimestampSource:
    name = cfg["timestamp_source"]
    cls = _TIMESTAMP_SOURCES.get(name)
    if cls is None:
        raise ValueError(f"Unknown timestamp_source: {name!r}")
    return cls()


def _build_sink(cfg: dict, venue: str) -> RecordSink:
    sink_cfg = cfg["sink"]
    sink_type = sink_cfg["type"]
    if sink_type == "local_parquet":
        return LocalParquetSink(
            base_dir=sink_cfg["base_dir"],
            venue=venue,
            batch_size=int(sink_cfg.get("batch_size", 1000)),
            flush_seconds=float(sink_cfg.get("flush_seconds", 5.0)),
        )
    if sink_type == "s3_parquet":
        return S3ParquetSink(
            bucket=os.path.expandvars(sink_cfg["bucket"]),
            prefix=sink_cfg["prefix"],
        )
    raise ValueError(f"Unknown sink type: {sink_type!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--venue",
        required=True,
        choices=sorted(EXCHANGES.keys()),
        help="Venue name; must match a key in collector.exchanges.EXCHANGES",
    )
    args = parser.parse_args()

    cfg = load_config()
    ts_source = _build_timestamp_source(cfg)
    sink = _build_sink(cfg, venue=args.venue)
    collector_cls = EXCHANGES[args.venue]
    collector = collector_cls(timestamp_source=ts_source, sink=sink)

    try:
        asyncio.run(collector.run())
    except KeyboardInterrupt:
        pass
    finally:
        sink.close()


if __name__ == "__main__":
    main()
