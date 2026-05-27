# Requirements: aws-ptp-crypto-recording

**Defined:** 2026-04-20
**Last updated:** 2026-05-08 (Kraken→OKX swap, Binance dual-stream, PTP-vs-NTP descoped per ADR-0011)
**Core Value:** Characterize feed latency and consolidated-book staleness with PTP-grade precision across five venues from five distinct AWS regions.

## v1 Requirements

### Architecture

- [ ] **ARCH-01**: TimestampSource abstract interface defined; ClockGettimeSource concrete implementation working
- [ ] **ARCH-02**: RecordSink abstract interface defined; LocalParquetSink concrete implementation writing to `./data/{venue}/{YYYY-MM-DD}/{HH}.parquet`
- [ ] **ARCH-03**: RecordSource abstract interface defined; LocalParquetSource concrete implementation iterating local Parquet shards
- [ ] **ARCH-04**: S3ParquetSink and S3ParquetSource concrete implementations using boto3
- [ ] **ARCH-05**: Config-driven environment via `RECORDING_CONFIG` env var; loads `config/recording.{env}.yaml` at collector and pipeline startup

### Collection

- [ ] **COLLECT-01**: Collector connects to Coinbase WS L2 depth feed and stays connected for at least 1 hour
- [ ] **COLLECT-02**: Collector connects to OKX WS L2 depth feed and stays connected for at least 1 hour
- [ ] **COLLECT-03**: Collector connects to Binance combined-stream `wss://data-stream.binance.vision/stream?streams=btcusdt@depth@100ms/btcusdt@trade` (dual-stream per ADR-0010) and stays connected for at least 1 hour
- [ ] **COLLECT-04**: Collector connects to Kalshi WS market data feed and stays connected for at least 1 hour
- [ ] **COLLECT-05**: Collector connects to Polymarket CLOB WS feed and stays connected for at least 1 hour
- [ ] **COLLECT-06**: Collector parses each WS message and extracts `t_exchange` from the venue payload
- [ ] **COLLECT-07**: Collector records NIC hardware timestamps via `SO_TIMESTAMPING` for every received TCP packet (C++ build only)
- [ ] **COLLECT-08**: Collector records per-packet metadata `(hw_ts, byte_count)` tuples for multi-packet WS messages

### Storage

- [ ] **STORE-01**: Each parsed message persists to Parquet using the schema in proposal § 6 (with HW timestamp fields zero-filled in the Python build)
- [ ] **STORE-02**: Parquet files are named `{venue}_{symbol}_{YYYYMMDD}_{HHmm}.parquet` or partitioned `{venue}/{YYYY-MM-DD}/{HH}.parquet`
- [ ] **STORE-03**: Parquet files are batched by venue and time window
- [ ] **STORE-04**: Parquet files sync from EC2 to S3 successfully via S3ParquetSink

### TickerPlant

- [ ] **TICKER-01**: Collector publishes parsed messages on a ZMQ pub/sub socket
- [ ] **TICKER-02**: Multiple subscribers consume the same feed concurrently without dropped messages
- [ ] **TICKER-03**: A file-writer subscriber persists messages to Parquet without blocking the publisher

### Time

- [ ] **TIME-01**: EC2 instance is PTP-synchronized via chrony with PHC0 as the selected reference, and `chronyc sources` shows stable sync
- [ ] **TIME-02**: Application code reads PTP-synced wall time via `clock_gettime(CLOCK_REALTIME)` exposed through PTPClockGettimeSource
- [ ] **TIME-03**: NIC hardware timestamps are captured via `SO_TIMESTAMPING` and `recvmsg` control messages in the C++ collector (NICHwTimestampSource)

### Book

- [ ] **BOOK-01**: System reconstructs a per-venue L2 book from REST snapshot plus diff stream, applying the documented `U`/`u`/`lastUpdateId` handshake
- [ ] **BOOK-02**: System merges per-venue books into a consolidated cross-venue BBO
- [ ] **BOOK-03**: System computes the consolidated BBO at three staleness windows (5ms, 10ms, 50ms)

### Lab

- [ ] **LAB-01**: Lab pipeline runs validator that detects gaps in `seq_num` per venue and logs them
- [ ] **LAB-02**: Lab pipeline runs continuously on a separate machine from collectors, pulling via S3ParquetSource, validating the two-tier architecture in practice

### Analytics

- [ ] **ANAL-01**: System produces per-venue feed latency distributions (mean, stdev, P50, P99, P999)
- [ ] **ANAL-02**: System produces time-of-day latency patterns and a volatility-correlation overlay
- [ ] **ANAL-04**: System produces per-message reassembly-duration analysis from `(hw_ts, byte_count)` metadata

## v2 Requirements

Deferred until professor scope is confirmed.

### AI / ML

- **ML-01**: Anomaly detection on the consolidated book (candidate)
- **ML-02**: Latency prediction from packet-level features (candidate)
- **ML-03**: NLP query interface over recorded data (candidate)

### Real-time

- **RT-01**: Real-time consolidated book reconstruction (live ZMQ subscriber merging feeds as they arrive)
- **RT-02**: Live BBO publication for downstream consumers

### Cross-market

- **XMKT-01**: Coinbase BTC move vs Polymarket prediction-market lead/lag analysis
- **XMKT-02**: Triangular consistency check (BTC/USDT, ETH/USDT, ETHBTC) using PTP timestamps

## Out of Scope

| Feature | Reason |
|---|---|
| Trading execution | Project is measurement and analysis, not trading |
| Order placement, cancellation, or account integration | No trading API surface in scope |
| L3 order-by-order data | Most venues do not offer publicly; volume too high for semester scope |
| Sub-millisecond accuracy on laptop measurements | Only AWS PTP-synced clock counts for final numbers; laptop is for sanity checks only |
| Binance perpetual futures or options | Different endpoint domain (`fstream` / `vstream`); separate US-access verification needed; not in proposal scope |
| Redis or database backends | Per professor; files only |
| PTP-vs-NTP merged-book comparison (former TIME-04 + ANAL-03) | Descoped from v1 per ADR-0011 (2026-05-08); not on critical path for cross-venue analysis. May be revisited as a v2 deliverable. |

## Traceability

| Requirement | Phase | Status |
|---|---|---|
| ARCH-01 | Phase 1 | Pending |
| ARCH-02 | Phase 1 | Pending |
| ARCH-03 | Phase 2 | Pending |
| ARCH-04 | Phase 3 | Pending |
| ARCH-05 | Phase 1 | Pending |
| COLLECT-01 | Phase 2 | Pending |
| COLLECT-02 | Phase 2 | Pending |
| COLLECT-03 | Phase 1 | Pending |
| COLLECT-04 | Phase 2 | Pending |
| COLLECT-05 | Phase 2 | Pending |
| COLLECT-06 | Phase 1 | Pending |
| COLLECT-07 | Phase 4 | Pending |
| COLLECT-08 | Phase 4 | Pending |
| STORE-01 | Phase 1 | Pending |
| STORE-02 | Phase 1 | Pending |
| STORE-03 | Phase 1 | Pending |
| STORE-04 | Phase 3 | Pending |
| TICKER-01 | Phase 4 | Pending |
| TICKER-02 | Phase 4 | Pending |
| TICKER-03 | Phase 4 | Pending |
| TIME-01 | Phase 3 | Pending |
| TIME-02 | Phase 3 | Pending |
| TIME-03 | Phase 4 | Pending |
| BOOK-01 | Phase 2 | Pending |
| BOOK-02 | Phase 2 | Pending |
| BOOK-03 | Phase 2 | Pending |
| LAB-01 | Phase 2 | Pending |
| LAB-02 | Phase 3 | Pending |
| ANAL-01 | Phase 2 | Pending |
| ANAL-02 | Phase 4 | Pending |
| ANAL-04 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 31 total (TIME-04 and ANAL-03 dropped per ADR-0011)
- Mapped to phases: 31
- Unmapped: 0 ✓

---

*Requirements defined: 2026-04-20*
*Last updated: 2026-05-08 after ADR-0009 (5-region), ADR-0010 (Binance dual-stream), ADR-0011 (PTP-vs-NTP descope)*
