"""Kalshi collector (cloud tier, us-east-2 Ohio).

Connects to wss://trading-api.kalshi.com/trade-api/ws/v2, subscribes to the
`orderbook_delta` channel for L2 order book updates on configured markets.
Kalshi sits closest to the Chicago metro from us-east-2.

Auth (Kalshi v2):
Kalshi requires API key plus an RSA-signed timestamp on every request,
including the WS handshake. The signing scheme is:

    1. Generate millisecond timestamp.
    2. Build msg = f"{timestamp_ms}{method}{path}"
       e.g. "1700000000000GET/trade-api/ws/v2"
    3. Sign msg with RSA-PSS using SHA-256 hash, MGF1 mask, max salt length.
    4. Base64-encode the signature.
    5. Send three headers on the WS handshake:
       - KALSHI-ACCESS-KEY: api_key_id
       - KALSHI-ACCESS-SIGNATURE: base64 of (4)
       - KALSHI-ACCESS-TIMESTAMP: timestamp_ms from (1)

This file lays out the structure but DOES NOT connect without working
credentials. To complete the wire-up:

    (a) `pip install cryptography>=42.0` and add it to requirements.txt
        under a "kalshi auth" group. The dep is heavy and is not yet
        required by any other connector.
    (b) Add `api_key_id` and `private_key_path` to config/exchanges.yaml
        under the `kalshi` entry. `private_key_path` points to a PEM-encoded
        RSA private key (absolute or relative to repo root).
    (c) The `NotImplementedError` in `run()` lifts automatically once both
        values are present in config.

Symbol shape: Kalshi tickers like `KXPRES-26-DJT`, `KXNCAAFCHAMP-26-ALA`.
TODO: Kalshi instruments expire and regenerate when events settle, so
the static exchanges.yaml symbols list is not viable long-term. Dynamic
instrument discovery via the REST `/markets` endpoint is a known
follow-up; for v1 the operator manually updates symbols at session start.

References:
- https://docs.kalshi.com/getting-started/authentication
- https://docs.kalshi.com/websocket-api/
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import websockets

from collector.base_collector import Collector
from collector.config_loader import load_exchanges

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    _CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    _CRYPTOGRAPHY_AVAILABLE = False


def _sign_kalshi_request(
    api_key_id: str,
    private_key_pem_path: str | Path,
    method: str,
    path: str,
) -> dict[str, str]:
    """Build the three KALSHI-ACCESS-* headers for the current instant.

    Deferred runtime check on the cryptography import so that this module
    still imports cleanly in test environments that lack the dep (e.g.
    laptop CI without auth credentials configured anyway).
    """
    if not _CRYPTOGRAPHY_AVAILABLE:
        raise NotImplementedError(
            "Kalshi auth requires the cryptography library. Install via "
            "`pip install cryptography>=42.0` and add it to requirements.txt "
            "before invoking this signing path."
        )

    private_key_pem = Path(private_key_pem_path).read_bytes()
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)

    timestamp_ms = str(int(time.time() * 1000))
    msg = f"{timestamp_ms}{method}{path}".encode("utf-8")

    signature = private_key.sign(
        msg,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    sig_b64 = base64.b64encode(signature).decode("ascii")

    return {
        "KALSHI-ACCESS-KEY": api_key_id,
        "KALSHI-ACCESS-SIGNATURE": sig_b64,
        "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
    }


class KalshiCollector(Collector):
    venue = "kalshi"
    endpoint = "wss://trading-api.kalshi.com/trade-api/ws/v2"
    ws_path = "/trade-api/ws/v2"

    async def run(self) -> None:
        cfg = load_exchanges()[self.venue]
        symbols = cfg.get("symbols") or []
        api_key_id = cfg.get("api_key_id")
        private_key_path = cfg.get("private_key_path")

        if not api_key_id or not private_key_path:
            raise NotImplementedError(
                "KalshiCollector requires kalshi_api_key_id and "
                "kalshi_private_key in config; signing implementation in TODO. "
                "Specifically: add `api_key_id` (string) and `private_key_path` "
                "(path to PEM-encoded RSA private key) to the kalshi entry in "
                "config/exchanges.yaml, and `pip install cryptography>=42.0`. "
                "See module docstring for the full Kalshi v2 auth spec; the "
                "signing helper _sign_kalshi_request is already implemented "
                "and waits on a real keypair to be useful."
            )
        if not symbols:
            raise ValueError("kalshi: exchanges.yaml has empty symbols list")

        headers = _sign_kalshi_request(
            api_key_id, private_key_path, "GET", self.ws_path,
        )

        async with websockets.connect(self.endpoint, additional_headers=headers) as ws:
            await ws.send(json.dumps({
                "id": 1,
                "cmd": "subscribe",
                "params": {
                    "channels": ["orderbook_delta"],
                    "market_tickers": list(symbols),
                },
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
        # subscribed/error/ok control responses arrive before data; ignore
        # anything that is not the data event we subscribed to.
        if msg.get("type") != "orderbook_delta":
            return None
        body = msg.get("msg") or {}
        ts_raw = body.get("ts")
        if ts_raw is None:
            return None
        # TODO(yichen): verify Kalshi v2 ts units. Doc text varies between
        # microseconds and milliseconds across endpoints. Treating as
        # microseconds here; once we have a live capture, compare against
        # wall-clock arrival to confirm and flip the scaling if needed.
        t_exchange_ns = int(ts_raw) * 1_000
        return {
            "venue": self.venue,
            "symbol": body.get("market_ticker", "UNKNOWN"),
            "stream": "orderbook_delta",
            "t_exchange_ns": t_exchange_ns,
            "payload_json": json.dumps(msg, separators=(",", ":")),
        }
