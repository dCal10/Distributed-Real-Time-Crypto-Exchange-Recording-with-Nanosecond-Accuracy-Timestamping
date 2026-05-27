"""Per-venue collectors plus a name to class registry.

The registry lets the entrypoint resolve `recording.{env}.yaml` venue names
to concrete collector classes without conditional imports. Each EC2 instance
runs one venue, selected at deploy time by config.
"""

from __future__ import annotations

from collector.base_collector import Collector
from collector.exchanges.binance import BinanceCollector
from collector.exchanges.binance_nic import BinanceNicCollector
from collector.exchanges.coinbase import CoinbaseCollector
from collector.exchanges.coinbase_nic import CoinbaseNicCollector
from collector.exchanges.kalshi import KalshiCollector
from collector.exchanges.okx import OKXCollector
from collector.exchanges.okx_nic import OKXNicCollector
from collector.exchanges.polymarket import PolymarketCollector

EXCHANGES: dict[str, type[Collector]] = {
    "binance": BinanceCollector,
    "binance_nic": BinanceNicCollector,
    "coinbase": CoinbaseCollector,
    "coinbase_nic": CoinbaseNicCollector,
    "okx": OKXCollector,
    "okx_nic": OKXNicCollector,
    "kalshi": KalshiCollector,
    "polymarket": PolymarketCollector,
}
