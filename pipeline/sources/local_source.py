"""LocalParquetSource: iterates records from ./data/.

Scaffold stub. Full implementation lives in Phase 2.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from pipeline.sources.base_source import RecordSource


class LocalParquetSource(RecordSource):
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)

    def __iter__(self) -> Iterator[dict]:
        # TODO: enumerate Parquet files under base_dir, yield records via PyArrow.
        # See lab-pipeline-prototype task for implementation.
        return iter([])
