"""LocalParquetSink: batched Parquet writer to ./data/{venue}/{YYYY-MM-DD}/{ns}.parquet.

Each flush writes a new Parquet file with the nanosecond timestamp at flush
time as filename. Parquet is write-once, so a single hourly file cannot be
appended to from multiple flushes; the day-partition directory collects all
sub-flush files instead. Schema is inferred from the buffered records via
pa.Table.from_pylist, which works for any venue's record shape.

Column-name normalization (ADR-0012, Step 4): the NIC timestamp source keeps
its natural Python field names (`t_nic_first`, `t_nic_last`) but they are
written to Parquet as `_ns`-suffixed columns for consistency with the
existing `t_exchange_ns` / `t_ptp_ns` / `delta_ns` columns. The rename is
applied here per-record and is a no-op for records that lack those keys, so
the production `binance` collector (which shares this sink) is unaffected:
its records have no `t_nic_*` keys, take the fast path, and write the exact
same 7-column inferred schema as before.

Backwards compatibility: no strict pyarrow schema is declared, so introducing
the new columns does not change or break existing production Parquet files
(those keep their inferred 7-column schema on disk). Querying production and
binance_nic data together must use DuckDB `read_parquet(..., union_by_name
=true)`, which fills the absent `t_nic_*_ns` / `packet_metadata` columns with
NULL for production rows. Schema-on-read, no migration needed.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from sinks.base_sink import RecordSink

_COLUMN_RENAMES = {
    "t_nic_first": "t_nic_first_ns",
    "t_nic_last": "t_nic_last_ns",
}


def _normalize(record: dict) -> dict:
    # Fast path: production records have none of the rename keys, so they are
    # returned untouched with zero dict-rebuild cost.
    if not any(k in record for k in _COLUMN_RENAMES):
        return record
    return {_COLUMN_RENAMES.get(k, k): v for k, v in record.items()}


class LocalParquetSink(RecordSink):
    def __init__(
        self,
        base_dir: str | Path,
        venue: str,
        batch_size: int = 1000,
        flush_seconds: float = 5.0,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.venue = venue
        self.batch_size = batch_size
        self.flush_seconds = flush_seconds
        self._buffer: list[dict] = []
        self._last_flush = time.monotonic()

    def write(self, record: dict) -> None:
        self._buffer.append(record)
        if len(self._buffer) >= self.batch_size:
            self.flush()
        elif time.monotonic() - self._last_flush >= self.flush_seconds:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            self._last_flush = time.monotonic()
            return

        now = datetime.now(timezone.utc)
        out_dir = self.base_dir / self.venue / now.strftime("%Y-%m-%d")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{time.time_ns()}.parquet"

        rows = [_normalize(r) for r in self._buffer]
        table = pa.Table.from_pylist(rows)
        pq.write_table(table, out_path)

        self._buffer.clear()
        self._last_flush = time.monotonic()

    def close(self) -> None:
        self.flush()
