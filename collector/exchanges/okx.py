"""OKX collector (cloud tier, ap-east-1 Hong Kong).

Connects to wss://ws.okx.com:8443/ws/v5/public, subscribes to `books`
(400-level L2 snapshot + incremental updates) and `trades` (per-trade events
analogous to Binance @trade). One combined subscribe message covers both
channels for all symbols.

OKX's matching engine runs on Alibaba Cloud Hong Kong, not AWS. AWS
ap-east-1 (Hong Kong) is the closest available collector vantage point but
is NOT co-located; this is intentional, the "near but not co-located" data
point in the cross-venue latency analysis. See ADR-0009.

References:
- https://www.okx.com/docs-v5/en/#order-book-trading-market-data
- https://www.okx.com/docs-v5/en/#websocket-api-public-channel-trades-channel

Notable differences from Binance's protocol:
- Subscribe is a single `op:subscribe` with an `args` list of {channel,instId}.
- Server sends an `event:subscribe` confirmation per arg before data flows;
  we filter these in `parse()` (they lack a `data` key).
- Timestamps come as millisecond strings (not ints); cast to int then scale.
- Instrument identifier uses dash format: BTC-USDT.
- Both `books` and `trades` carry a per-message `ts` field at data[0].ts.
"""

from __future__ import annotations

import json

import websockets

from collector.base_collector import Collector
from collector.config_loader import load_exchanges

CHANNELS = ("books", "trades")


class OKXCollector(Collector):
    venue = "okx"
    endpoint = "wss://ws.okx.com:8443/ws/v5/public"

    async def run(self) -> None:
        cfg = load_exchanges()[self.venue]
        symbols = cfg.get("symbols") or []
        if not symbols:
            raise ValueError("okx: exchanges.yaml has empty symbols list")

        args = [
            {"channel": ch, "instId": sym}
            for sym in symbols
            for ch in CHANNELS
        ]
        sub_msg = json.dumps({"op": "subscribe", "args": args})

        async with websockets.connect(self.endpoint) as ws:
            await ws.send(sub_msg)
            while True:
                raw = await ws.recv()
                t_ptp_ns = self.timestamp_source.capture().t_userspace
                record = self.parse(raw)
                if record is None:
                    continue
                record["t_ptp_ns"] = t_ptp_ns
                record["delta_ns"] = t_ptp_ns - record["t_exchange_ns"]
                self.sink.write(record)

    def parse(self, raw: str | bytes) -> dict | None:
        msg = json.loads(raw)
        # Subscription confirmations have `event` key, no `data` key.
        # Errors also surface under `event`. Filter both.
        if "event" in msg or "data" not in msg:
            return None
        data = msg.get("data") or []
        if not data:
            return None
        ts_str = data[0].get("ts")
        if ts_str is None:
            return None
        arg = msg.get("arg") or {}
        return {
            "venue": self.venue,
            "symbol": arg.get("instId", "UNKNOWN"),
            "stream": arg.get("channel", "UNKNOWN"),
            "t_exchange_ns": int(ts_str) * 1_000_000,
            "payload_json": json.dumps(msg, separators=(",", ":")),
        }
