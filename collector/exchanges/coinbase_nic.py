"""Coinbase NIC-hardware-timestamp collector (ADR-0012, deploy-ready for us-east-1).

Subclass of `CoinbaseCollector` that overrides only `run()` to use the
raw-socket transport (`RawWebSocketClient`) plus per-message
`NICTimestampSource` instead of the high-level `websockets` library. `parse()`
is inherited unchanged, so the WS payload is parsed identically and the
record's `venue` field stays "coinbase" (this IS Coinbase data; only the
collection method differs). Same subclass-and-override-run() pattern as
`binance_nic.py`.

The two collectors coexist:
  - production `--venue coinbase`     -> websockets + configured TimestampSource,
                                         writes data/coinbase/
  - this     `--venue coinbase_nic`   -> raw socket + NIC HW timestamps,
                                         writes data/coinbase_nic/
The sink directory is split by the entrypoint's `--venue` argument; the
record `venue` field is "coinbase" in both. Production `coinbase` keeps the
clock_gettime baseline path available if we ever want it.

Protocol differences from binance_nic that shape this run():
  - Coinbase has no combined-stream URL. The subscription is sent as JSON
    AFTER the WS handshake completes, one `subscribe` message per channel
    (CHANNELS = market_trades + ticker). `RawWebSocketClient.connect()`
    finishes only the handshake, so we call the new `client.send()` (added
    to RawWebSocketClient) once per channel before entering the messages()
    loop. The WS handshake target therefore has no path component ("/").
  - `CoinbaseCollector.parse()` returns None for the `subscriptions`
    confirmation frame and any control frame without a timestamp; that
    None-filter is preserved here exactly as in the production run().

Production safety: `RawWebSocketClient` (and its `wsproto` dependency) is
imported lazily inside `run()`, NOT at module top, mirroring binance_nic.
`collector.exchanges` imports every venue module at load. Keeping the
wsproto import out of module scope means a box that has not yet run
`pip install -r requirements.txt` can still start a non-NIC venue without
an ImportError. `json` and the parent `CHANNELS` constant are stdlib /
already-loaded and safe at module scope.
"""

from __future__ import annotations

import json

from collector.exchanges.coinbase import CHANNELS, CoinbaseCollector


class CoinbaseNicCollector(CoinbaseCollector):
    # venue stays "coinbase" (inherited): config lookup + parse() unchanged.
    # The coinbase_nic distinction is the sink path, set by entrypoint --venue.

    async def run(self) -> None:
        # Lazy imports: keep collector.exchanges importable without wsproto so
        # the production --venue coinbase path is unaffected (see module docstring).
        from collector.config_loader import load_exchanges
        from collector.timestamp.nic_hw_source import NICTimestampSource
        from collector.transport.raw_ws import RawWebSocketClient

        symbols = load_exchanges()[self.venue].get("symbols") or []
        if not symbols:
            raise ValueError("coinbase_nic: exchanges.yaml has empty symbols list")

        host = self.endpoint.removeprefix("wss://")
        client = RawWebSocketClient(host=host, path="/")
        await client.connect()
        try:
            for channel in CHANNELS:
                await client.send(json.dumps({
                    "type": "subscribe",
                    "product_ids": list(symbols),
                    "channel": channel,
                }))
            async for payload, chunks in client.messages():
                ts = NICTimestampSource(list(chunks)).capture()
                record = self.parse(payload)
                if record is None:
                    continue
                record["t_ptp_ns"] = ts.t_userspace
                record["t_nic_first"] = ts.t_nic_first
                record["t_nic_last"] = ts.t_nic_last
                record["packet_metadata"] = [
                    {"t_ns": t_ns, "byte_count": byte_count}
                    for t_ns, byte_count in ts.packet_metadata
                ]
                record["delta_ns"] = ts.t_userspace - record["t_exchange_ns"]
                self.sink.write(record)
        finally:
            await client.close()
