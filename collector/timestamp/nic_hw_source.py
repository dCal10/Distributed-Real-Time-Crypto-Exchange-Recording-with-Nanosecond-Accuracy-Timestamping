"""NIC hardware timestamp sources.

Two classes live here:

`NICTimestampSource` (ADR-0012, the working path): holds the per-TCP-chunk
NIC arrival timestamps for one assembled WS message and exposes them through
the standard `TimestampSource` interface. It does NOT call `recvmsg` itself;
the new raw-socket collector (collector/transport/raw_ws.py, consumed by
collector/exchanges/binance_nic.py) performs the `SO_TIMESTAMPING` recvmsg
and per-chunk timestamping, then constructs this class with the collected
`(t_ns, byte_count)` tuples for the message being stamped.

`NICHwTimestampSource` (kept, registry stub): still imported by
collector/entrypoint.py and registered as the `nic_hw` config option. It is
intentionally left raising NotImplementedError. The NIC path is NOT reachable
through the no-argument config-registry instantiation (`cls()`); it requires
the new collector that supplies per-message chunk timestamps. This class is
preserved unchanged so the production entrypoint import keeps working; the
Tokyo `group19-collector@binance` service imports collector.entrypoint at
process start and must not break.

The earlier "Python cannot access SO_TIMESTAMPING" framing was a misreading.
The high-level `websockets` library buffers ahead of the kernel socket
(Q7 spike, tests/spike_so_timestamping.py), but a raw socket + ssl.MemoryBIO
+ wsproto path can read the ancillary data. See ADR-0012.
"""

from __future__ import annotations

import time

from collector.timestamp.base import TimestampSource, Timestamps


class NICTimestampSource(TimestampSource):
    """Per-message NIC chunk timestamps exposed as a `Timestamps` value.

    Construct with the ordered list of `(t_ns, byte_count)` tuples for every
    TCP chunk that contributed to one assembled WS message. `capture()`
    derives `t_nic_first` / `t_nic_last` from the first / last chunk and reads
    `t_userspace` via `time.time_ns()` at call time, so the userspace
    clock_gettime path is retained alongside the hardware stamp for direct
    jitter comparison.
    """

    precision_label = "SO_TIMESTAMPING (NIC hardware via wsproto+MemoryBIO, ADR-0012)"

    def __init__(self, chunk_timestamps: list[tuple[int, int]]) -> None:
        self._chunks: tuple[tuple[int, int], ...] = tuple(chunk_timestamps)

    def capture(self) -> Timestamps:
        userspace = time.time_ns()
        if self._chunks:
            t_nic_first = self._chunks[0][0]
            t_nic_last = self._chunks[-1][0]
        else:
            # Timestamps documents 0 as the "not available" sentinel. A
            # message with no recorded chunks should not occur, but emitting
            # a well-formed record beats raising mid-stream and killing the
            # collector over one anomalous frame.
            t_nic_first = 0
            t_nic_last = 0
        return Timestamps(
            t_nic_first=t_nic_first,
            t_nic_last=t_nic_last,
            t_userspace=userspace,
            packet_metadata=self._chunks,
        )


class NICHwTimestampSource(TimestampSource):
    """Registry-facing stub. Kept for collector/entrypoint.py import and the
    `nic_hw` config option. The working NIC path is `NICTimestampSource`,
    supplied per-message by the binance_nic collector, not the no-argument
    config registry. Selecting `nic_hw` via RECORDING_CONFIG still errors by
    design.
    """

    precision_label = "SO_TIMESTAMPING (stub; use the binance_nic collector, not this)"

    def capture(self) -> Timestamps:
        raise NotImplementedError(
            "NICHwTimestampSource is the config-registry stub. The working "
            "NIC hardware path is NICTimestampSource, supplied per-message by "
            "the binance_nic collector (collector/transport/raw_ws.py). Do "
            "not select nic_hw via RECORDING_CONFIG; run --venue binance_nic "
            "instead. See ADR-0012."
        )
