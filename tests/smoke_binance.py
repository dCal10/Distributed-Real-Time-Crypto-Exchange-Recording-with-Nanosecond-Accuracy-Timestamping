"""Smoke test: pull five Binance @depth messages and print them.

Quick sanity check that the venv, network, and asyncio loop are wired up before
building out collector/binance.py. Not a pytest test; the filename is
deliberately smoke_* so pytest does not auto-collect it.

Each header reports `local - E` in milliseconds, where `local` is time.time_ns()
captured immediately after recv() returns and `E` is Binance's event-time field.
On a laptop with NTP-synced clock this carries tens to hundreds of ms of
clock-skew error, so the shape across messages is informative but the absolute
value is not. The production C++ collector replaces both terms with NIC HW
timestamps on a PTP-synced clock and removes that error.

Run directly:

    python tests/smoke_binance.py
"""

from __future__ import annotations

import asyncio
import json
import time

import websockets

# data-stream.binance.vision is Binance's documented public-data mirror.
# stream.binance.com:9443 returns HTTP 451 from US IPs; see docs/proposal.md
# section 5 and the closed Binance question in docs/questions.md.
# Endpoint confirmed reachable from a US IP on 2026-05-08.
ENDPOINT = "wss://data-stream.binance.vision"

# Subscribe to btcusdt@depth for connectivity. The production collector uses
# @depth@100ms + @trade per ADR-0010 (empirical 2026-05-08 evidence showed
# @depth flushes at ~1 Hz at the WS layer, so unbatched does not preserve
# sub-second cadence the way ADR-0006 originally claimed). This smoke test
# is a wire-up check and does not depend on the stream choice.
STREAM = "btcusdt@depth"

NUM_MESSAGES = 5


async def main() -> None:
    uri = f"{ENDPOINT}/ws/{STREAM}"
    async with websockets.connect(uri) as ws:
        for i in range(NUM_MESSAGES):
            raw = await ws.recv()
            t_local_ns = time.time_ns()
            msg = json.loads(raw)
            delta_ms = (t_local_ns / 1_000_000) - msg["E"]
            print(
                f"--- message {i + 1}/{NUM_MESSAGES} "
                f"| local - E = {delta_ms:+.1f} ms ---"
            )
            print(json.dumps(msg, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
