"""TimestampSource abstract interface and Timestamps dataclass.

The Timestamps shape mirrors the per-message schema in proposal section 6.
Sources differ in *precision* of the underlying clock and in whether NIC-level
timestamps are available. Downstream code never inspects the source type; it
only consumes Timestamps values.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Timestamps:
    t_nic_first: int  # ns since epoch; 0 when not available
    t_nic_last: int   # ns since epoch; 0 when not available
    t_userspace: int  # ns since epoch; clock_gettime after parse
    packet_metadata: tuple[tuple[int, int], ...]  # ((hw_ts, byte_count), ...)


class TimestampSource(ABC):
    @abstractmethod
    def capture(self) -> Timestamps:
        """Return Timestamps as of now. Call immediately after WS recv()."""

    @property
    @abstractmethod
    def precision_label(self) -> str:
        """Human-readable label for the precision regime; used in logs."""
