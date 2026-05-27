"""PTPClockGettimeSource: marker subclass for the PTP-disciplined regime.

On EC2 instances with chrony locked to PHC0, `clock_gettime(CLOCK_REALTIME)`
returns a PTP-disciplined wall clock. The capture path is identical to
`ClockGettimeSource`: `time.time_ns()` is a CPython builtin that calls
`clock_gettime` directly via vDSO with ~100 ns of total wrapper overhead. An
earlier ctypes implementation was measurably slower (~1.8 us per call on
darwin) and was removed; selecting this class via `RECORDING_CONFIG=aws` is
purely a label change so logs and analysis can distinguish the
PTP-disciplined regime from the laptop NTP regime.

Verify before relying on PTP precision: `chronyc sources` should show `^* PHC0`
with a stable offset.
"""

from __future__ import annotations

from collector.timestamp.clock_gettime_source import ClockGettimeSource


class PTPClockGettimeSource(ClockGettimeSource):
    precision_label = "clock_gettime(REALTIME) (PTP-disciplined via chrony+PHC0)"
