"""S3ParquetSink: writes Parquet shards locally then syncs to S3.

Stub. Full implementation lives in Phase 3 (cloud deployment).
"""

from __future__ import annotations

from sinks.base_sink import RecordSink


class S3ParquetSink(RecordSink):
    def __init__(self, bucket: str, prefix: str, **kwargs) -> None:
        self.bucket = bucket
        self.prefix = prefix

    def write(self, record: dict) -> None:
        raise NotImplementedError("S3ParquetSink is implemented in Phase 3.")

    def flush(self) -> None:
        raise NotImplementedError("S3ParquetSink is implemented in Phase 3.")

    def close(self) -> None:
        raise NotImplementedError("S3ParquetSink is implemented in Phase 3.")
