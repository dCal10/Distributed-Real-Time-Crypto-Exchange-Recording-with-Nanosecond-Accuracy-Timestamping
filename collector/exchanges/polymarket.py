"""Polymarket CLOB collector (cloud tier, eu-west-2 London).

Connects to wss://ws-subscriptions-clob.polymarket.com/ws/, subscribes to
the "Market" channel for L2 order book updates on configured assets.
Public feed, no authentication.

KEY LIMIT: Polymarket allows up to 500 asset_ids per WS subscription. The
class refuses to start above that count, with a TODO directing the operator
to the multi-connection pattern needed for larger captures. For v1 scope
(one BTC condition + a handful of headline markets) a single connection is
sufficient; the structural change to N parallel connections fanning into a
single sink is a known follow-up.

Symbol shape: Polymarket asset_ids are 32-byte hex condition IDs. They map
to specific YES/NO outcomes on specific markets. Like Kalshi, instruments
resolve and re-generate as events settle; static config in exchanges.yaml
is acceptable for v1 but will need dynamic discovery via the Polymarket
gamma REST API for any sustained run.

References:
- https://docs.polymarket.com/developers/CLOB/introduction
- https://docs.polymarket.com/developers/CLOB/websocket/wss-overview
"""

from __future__ import annotations

import json

import websockets

from collector.base_collector import Collector
from collector.config_loader import load_exchanges

POLYMARKET_MAX_ASSETS_PER_CONN = 500


class PolymarketCollector(Collector):
    venue = "polymarket"
    endpoint = "wss://ws-subscriptions-clob.polymarket.com/ws/"

    async def run(self) -> None:
        cfg = load_exchanges()[self.venue]
        symbols = cfg.get("symbols") or []
        if not symbols:
            raise ValueError("polymarket: exchanges.yaml has empty symbols list")
        if len(symbols) > POLYMARKET_MAX_ASSETS_PER_CONN:
            raise NotImplementedError(
                f"Polymarket subscription cap is {POLYMARKET_MAX_ASSETS_PER_CONN} "
                f"assets per connection; got {len(symbols)}. Multi-connection "
                "support is a known TODO: spawn N parallel websocket "
                "connections, each subscribed to <=500 asset_ids, fanning into "
                "one sink. See module docstring for context."
            )

        async with websockets.connect(self.endpoint) as ws:
            await ws.send(json.dumps({
                "type": "Market",
                # Polymarket's documented field is `assets_ids` (plural 'assets',
                # plural 'ids'); the apparent typo is part of the live API. If
                # subscription fails with "unknown field assets_ids", flip to
                # "asset_ids" and update this comment.
                "assets_ids": list(symbols),
            }))
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
        # Polymarket emits event_type values of "book" (full L2 snapshot),
        # "price_change" (level update), "tick_size_change" (parameter
        # change). All are useful for the latency analysis. Pong / control
        # frames lack event_type and are skipped here.
        event_type = msg.get("event_type")
        if event_type is None:
            return None
        ts_raw = msg.get("timestamp")
        if ts_raw is None:
            return None
        t_exchange_ns = int(ts_raw) * 1_000_000
        return {
            "venue": self.venue,
            "symbol": msg.get("asset_id") or msg.get("market") or "UNKNOWN",
            "stream": event_type,
            "t_exchange_ns": t_exchange_ns,
            "payload_json": json.dumps(msg, separators=(",", ":")),
        }
