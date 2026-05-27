"""S3ParquetSource: iterates records from s3://{bucket}/{prefix}/.

Stub. Full implementation lives in Phase 3.
"""

from __future__ import annotations

from typing import Iterator

from pipeline.sources.base_source import RecordSource


class S3ParquetSource(RecordSource):
    def __init__(self, bucket: str, prefix: str) -> None:
        self.bucket = bucket
        self.prefix = prefix

    def __iter__(self) -> Iterator[dict]:
        raise NotImplementedError("S3ParquetSource is implemented in Phase 3.")
