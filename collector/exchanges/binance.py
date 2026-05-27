"""Binance collector (cloud tier, ap-northeast-1).

Connects to wss://data-stream.binance.vision/stream and consumes a combined
subscription of @depth@100ms (10 Hz orderbook deltas) plus @trade (per-event
matching-engine timestamps via the T field). The .com host returns HTTP 451
from US IPs (regulatory geo-block, validated 2026-04-20); .vision is the
public alternative.

Why both streams: empirical observation on 2026-05-08 showed @depth (the
unbatched diff) flushes at 1 Hz with ~130 matching-engine events bundled per
WS frame. @depth therefore does not preserve sub-second event-level granularity
any more than @depth@100ms does. @depth@100ms gives 10x finer cadence for
orderbook reconstruction; @trade carries per-event matching-engine timestamps
(T field) inside payload_json for downstream latency decomposition. Together
they recover what @depth alone cannot.
"""

from __future__ import annotations

import json

import websockets

from collector.base_collector import Collector
from collector.config_loader import load_exchanges


class BinanceCollector(Collector):
    venue = "binance"
    endpoint = "wss://data-stream.binance.vision"

    async def run(self) -> None:
        symbols = load_exchanges()[self.venue].get("symbols") or []
        if not symbols:
            raise ValueError("binance: exchanges.yaml has empty symbols list")

        parts: list[str] = []
        for sym in symbols:
            parts.append(f"{sym.lower()}@depth@100ms")
            parts.append(f"{sym.lower()}@trade")
        uri = f"{self.endpoint}/stream?streams={'/'.join(parts)}"

        async with websockets.connect(uri) as ws:
            while True:
                raw = await ws.recv()
                t_ptp_ns = self.timestamp_source.capture().t_userspace
                record = self.parse(raw)
                record["t_ptp_ns"] = t_ptp_ns
                record["delta_ns"] = t_ptp_ns - record["t_exchange_ns"]
                self.sink.write(record)

    def parse(self, raw: str | bytes) -> dict:
        wrapper = json.loads(raw)
        data = wrapper["data"]
        return {
            "venue": self.venue,
            "symbol": data["s"],
            "stream": wrapper["stream"],
            "t_exchange_ns": int(data["E"]) * 1_000_000,
            "payload_json": json.dumps(data, separators=(",", ":")),
        }
