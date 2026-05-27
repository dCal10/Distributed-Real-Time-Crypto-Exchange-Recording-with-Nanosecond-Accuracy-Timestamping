"""ClockGettimeSource: laptop-grade timestamping via time.time_ns().

Wraps `clock_gettime(CLOCK_REALTIME)` (which is what `time.time_ns()` maps to
on Linux and macOS). NTP-disciplined at best on a laptop, suitable for prototype
development but NOT for cross-venue measurement claims. Used when
RECORDING_CONFIG=local.
"""

from __future__ import annotations

import time

from collector.timestamp.base import TimestampSource, Timestamps


class ClockGettimeSource(TimestampSource):
    precision_label = "clock_gettime(REALTIME) (NTP-disciplined)"

    def capture(self) -> Timestamps:
        ns = time.time_ns()
        return Timestamps(
            t_nic_first=ns,
            t_nic_last=ns,
            t_userspace=ns,
            packet_metadata=(),
        )
