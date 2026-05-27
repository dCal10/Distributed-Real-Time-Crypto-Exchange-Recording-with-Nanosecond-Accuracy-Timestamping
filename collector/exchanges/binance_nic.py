"""Binance NIC-hardware-timestamp collector (ADR-0012, Step 3).

Subclass of `BinanceCollector` that overrides only `run()` to use the
raw-socket transport (`RawWebSocketClient`) and per-message
`NICTimestampSource` instead of the high-level `websockets` library. `parse()`
is inherited unchanged, so the WS payload is parsed identically and the
record's `venue` field stays "binance" (this IS Binance data; only the
collection method differs).

The two collectors coexist:
  - production `--venue binance`     -> websockets + PTPClockGettimeSource,
                                        writes data/binance/
  - this     `--venue binance_nic`   -> raw socket + NIC HW timestamps,
                                        writes data/binance_nic/
The sink directory is split by the entrypoint's `--venue` argument; the
record `venue` field is "binance" in both. Run side-by-side for comparison.

Production safety: `RawWebSocketClient` (and its `wsproto` dependency) is
imported lazily inside `run()`, NOT at module top. `collector.exchanges`
imports every venue module at load, including this one, even when the
production `--venue binance` path is selected. Keeping the wsproto import
out of module scope means a Tokyo box that has not yet run
`pip install -r requirements.txt` can still start `group19-collector@binance`
without an ImportError. Only actually selecting `--venue binance_nic`
requires wsproto.
"""

from __future__ import annotations

from collector.exchanges.binance import BinanceCollector


class BinanceNicCollector(BinanceCollector):
    # venue stays "binance" (inherited): config lookup + parse() unchanged.
    # The binance_nic distinction is the sink path, set by entrypoint --venue.

    async def run(self) -> None:
        # Lazy imports: keep collector.exchanges importable without wsproto so
        # the production --venue binance path is unaffected (see module docstring).
        from collector.config_loader import load_exchanges
        from collector.timestamp.nic_hw_source import NICTimestampSource
        from collector.transport.raw_ws import RawWebSocketClient

        symbols = load_exchanges()[self.venue].get("symbols") or []
        if not symbols:
            raise ValueError("binance_nic: exchanges.yaml has empty symbols list")

        parts: list[str] = []
        for sym in symbols:
            parts.append(f"{sym.lower()}@depth@100ms")
            parts.append(f"{sym.lower()}@trade")
        host = self.endpoint.removeprefix("wss://")
        path = f"/stream?streams={'/'.join(parts)}"

        client = RawWebSocketClient(host=host, path=path)
        await client.connect()
        try:
            async for payload, chunks in client.messages():
                ts = NICTimestampSource(list(chunks)).capture()
                record = self.parse(payload)
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
