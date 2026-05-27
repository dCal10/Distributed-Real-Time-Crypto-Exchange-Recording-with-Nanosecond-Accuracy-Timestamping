"""Abstract Collector interface.

Each venue subclasses to wire WS endpoint and message parsing while reusing
shared timestamp + sink plumbing. Subclasses implement `run()` (the connect
and stream loop) and `parse()` (venue-specific message format).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from collector.timestamp.base import TimestampSource
from sinks.base_sink import RecordSink


class Collector(ABC):
    venue: str

    def __init__(self, timestamp_source: TimestampSource, sink: RecordSink) -> None:
        self.timestamp_source = timestamp_source
        self.sink = sink

    @abstractmethod
    async def run(self) -> None:
        """Connect to the WS feed and stream parsed records to the sink."""

    @abstractmethod
    def parse(self, raw: str | bytes) -> dict:
        """Parse one venue-specific WS message into the canonical record schema."""
