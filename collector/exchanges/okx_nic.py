"""OKX NIC-hardware-timestamp collector (ADR-0012, deploy-ready for ap-east-1).

Subclass of `OKXCollector` that overrides only `run()` to use the raw-socket
transport (`RawWebSocketClient`) plus per-message `NICTimestampSource`
instead of the high-level `websockets` library. `parse()` is inherited
unchanged, so the WS payload is parsed identically and the record's `venue`
field stays "okx" (this IS OKX data; only the collection method differs).
Same subclass-and-override-run() pattern as `binance_nic.py`.

The two collectors coexist:
  - production `--venue okx`     -> websockets + configured TimestampSource,
                                    writes data/okx/
  - this     `--venue okx_nic`   -> raw socket + NIC HW timestamps,
                                    writes data/okx_nic/
The sink directory is split by the entrypoint's `--venue` argument; the
record `venue` field is "okx" in both. Production `okx` keeps the
clock_gettime baseline path available if we ever want it.

Protocol differences from binance_nic that shape this run():
  - OKX has no combined-stream URL. After the WS handshake we send a single
    `op:subscribe` JSON whose `args` list carries one {channel, instId}
    object per (channel, instrument) pair (CHANNELS = books + trades),
    built identically to the production `OKXCollector.run()`. We use the
    `client.send()` added to RawWebSocketClient, once, before the
    messages() loop.
  - OKX's endpoint is wss://ws.okx.com:8443/ws/v5/public: a non-default
    port AND a URL path, unlike Binance's bare host. `urlsplit` separates
    host / port / path so RawWebSocketClient connects the TCP socket to
    :8443 and issues the WS handshake against /ws/v5/public.
  - `OKXCollector.parse()` returns None for the per-arg `event:subscribe`
    confirmation frames (they carry `event`, no `data`); that None-filter
    is preserved here exactly as in the production run(). The NIC path
    decodes byte-identical WS frames in the same order as the websockets
    path, so the parent's confirmation filtering is unaffected.

Host-header note: RawWebSocketClient reuses `server_hostname` for both TLS
SNI and the WS `Host` header. SNI MUST be the bare hostname (a port in SNI
breaks certificate validation), so the WS Host header is sent as
"ws.okx.com" without the :8443 suffix. OKX's dedicated WS endpoint routes
purely by the established TCP connection, so a port-less Host header is
accepted. This assumption is documented in the morning summary as an open
item to confirm on first ap-east-1 connect; splitting SNI from the Host
header would require modifying the shared production transport, which is
out of scope here.

Production safety: `RawWebSocketClient` (and its `wsproto` dependency) is
imported lazily inside `run()`, NOT at module top, mirroring binance_nic.
`json`, `urlsplit`, and the parent `CHANNELS` constant are stdlib /
already-loaded and safe at module scope.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from collector.exchanges.okx import CHANNELS, OKXCollector


class OKXNicCollector(OKXCollector):
    # venue stays "okx" (inherited): config lookup + parse() unchanged.
    # The okx_nic distinction is the sink path, set by entrypoint --venue.

    async def run(self) -> None:
        # Lazy imports: keep collector.exchanges importable without wsproto so
        # the production --venue okx path is unaffected (see module docstring).
        from collector.config_loader import load_exchanges
        from collector.timestamp.nic_hw_source import NICTimestampSource
        from collector.transport.raw_ws import RawWebSocketClient

        cfg = load_exchanges()[self.venue]
        symbols = cfg.get("symbols") or []
        if not symbols:
            raise ValueError("okx_nic: exchanges.yaml has empty symbols list")

        args = [
            {"channel": ch, "instId": sym}
            for sym in symbols
            for ch in CHANNELS
        ]
        sub_msg = json.dumps({"op": "subscribe", "args": args})

        split = urlsplit(self.endpoint)
        host = split.hostname or ""
        port = split.port or 443
        path = split.path or "/"

        client = RawWebSocketClient(host=host, path=path, port=port)
        await client.connect()
        try:
            await client.send(sub_msg)
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
