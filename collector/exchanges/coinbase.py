"""Coinbase Advanced Trade collector (cloud tier, us-east-1).

Connects to wss://advanced-trade-ws.coinbase.com, subscribes to two PUBLIC
channels in parallel: `market_trades` (per-trade events, analogous to Binance
@trade) and `ticker` (best bid/ask updates, the closest unauthenticated
substitute for L2 depth).

LIMITATION: full L2 (`level2` channel) on Coinbase Advanced Trade requires
API-key authentication. We subscribe to the unauthenticated subset for now;
when Yichen plugs in API keys, add `level2` to `CHANNELS` and remove this
note. The `ticker` channel gives best bid/ask + size only, not the full
order book ladder, so consolidated-book reconstruction across venues will
have shallower depth for Coinbase than for Binance/OKX until that lands.

References:
- https://docs.cdp.coinbase.com/advanced-trade/docs/ws-overview
- https://docs.cdp.coinbase.com/advanced-trade/docs/ws-channels

Notable differences from Binance's protocol:
- Subscription model: one `subscribe` message per channel (we send 2).
- Timestamps arrive as ISO 8601 strings, not ms-since-epoch ints; parsed
  via `datetime.fromisoformat`.
- Server sends a `subscriptions` confirmation message before data flows;
  we filter these in `parse()` by returning None.
- Product identifier uses dash format: BTC-USD, ETH-USD.
"""

from __future__ import annotations

import json
from datetime import datetime

import websockets

from collector.base_collector import Collector
from collector.config_loader import load_exchanges

CHANNELS = ("market_trades", "ticker")


def _iso_to_ns(iso: str) -> int:
    """Parse an ISO 8601 timestamp to nanoseconds since epoch.

    Handles trailing Z (datetime.fromisoformat requires +00:00 in some
    older runtime versions; the replace is cheap insurance).
    """
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return int(dt.timestamp() * 1_000_000_000)


class CoinbaseCollector(Collector):
    venue = "coinbase"
    endpoint = "wss://advanced-trade-ws.coinbase.com"

    async def run(self) -> None:
        cfg = load_exchanges()[self.venue]
        symbols = cfg.get("symbols") or []
        if not symbols:
            raise ValueError("coinbase: exchanges.yaml has empty symbols list")

        async with websockets.connect(self.endpoint) as ws:
            for channel in CHANNELS:
                await ws.send(json.dumps({
                    "type": "subscribe",
                    "product_ids": list(symbols),
                    "channel": channel,
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
        channel = msg.get("channel")
        # Subscription confirmations carry channel="subscriptions" with no
        # timestamp; control/error frames may also lack the keys we need.
        if channel in (None, "subscriptions"):
            return None
        ts_iso = msg.get("timestamp")
        if ts_iso is None:
            return None
        events = msg.get("events") or []
        symbol = self._first_product_id(events, channel)
        return {
            "venue": self.venue,
            "symbol": symbol,
            "stream": channel,
            "t_exchange_ns": _iso_to_ns(ts_iso),
            "payload_json": json.dumps(msg, separators=(",", ":")),
        }

    @staticmethod
    def _first_product_id(events: list, channel: str) -> str:
        # market_trades events have events[].trades[]; ticker events have
        # events[].tickers[]. Both inner objects carry product_id. We take
        # the first one we find as the record's symbol; a single WS frame
        # may contain events for multiple symbols inside payload_json, so
        # this is "the dominant symbol" not "the only symbol."
        for ev in events or []:
            for inner_key in ("trades", "tickers"):
                inner = ev.get(inner_key) or []
                if inner:
                    pid = inner[0].get("product_id")
                    if pid:
                        return pid
        return "UNKNOWN"
