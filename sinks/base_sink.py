"""RecordSink abstract interface.

All concrete sinks accept dict records and batch them according to their own
flush policy (count threshold, time threshold, or both).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class RecordSink(ABC):
    @abstractmethod
    def write(self, record: dict) -> None:
        """Append one record. Sink may buffer until a flush threshold is hit."""

    @abstractmethod
    def flush(self) -> None:
        """Force any buffered records to be persisted."""

    @abstractmethod
    def close(self) -> None:
        """Flush remaining buffer and release resources."""
