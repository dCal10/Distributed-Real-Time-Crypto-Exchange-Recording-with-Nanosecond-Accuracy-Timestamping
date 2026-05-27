"""RecordSource abstract interface.

Iterates persisted records back into the lab pipeline. Counterpart of RecordSink.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator


class RecordSource(ABC):
    @abstractmethod
    def __iter__(self) -> Iterator[dict]:
        """Yield records in chronological order across the configured time window."""
