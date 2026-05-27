# Project Proposal: aws-ptp-crypto-recording

> **Status**: Draft — expect major pivots as professor guidance and VM provisioning solidify.
> **Last updated**: 2026-04-20

---

## 1. Problem Statement

Exchange timestamps are self-reported and unverifiable. Each exchange has its own clock, its own internal latency before stamping, and its own definition of "when" an event occurred. There is no common reference clock across venues, so comparing timestamps between Coinbase and Binance is comparing two untrusted sources.

Crypto has no equivalent of the SIP (Securities Information Processor) that exists in US equities — no centralized consolidated feed. Anyone wanting a unified view of liquidity across exchanges must build it themselves, and doing so accurately requires knowing *when* each venue's data actually arrived.

## 2. What We're Building

A pipeline that:

1. Connects to multiple crypto exchanges and prediction markets via websocket
2. Captures L2 order book data with NIC-level hardware timestamps (PTP-synced via AWS TimeSync)
3. Records raw data to Parquet files while simultaneously publishing via a ticker plant to downstream consumers
4. Reconstructs a consolidated order book across venues
5. Analyzes cross-venue feed latency, book staleness, and the precision boundary where NTP stops being useful

This is a measurement and recording infrastructure project, not a trading system.

## 3. Architecture

```
Exchange WS Feeds (5 venues)
    │
    ▼
Collector (one per venue, C/C++ hot path)
    │  ← HW NIC timestamp via SO_TIMESTAMPING on each packet
    │  ← Track bytes-per-packet arrival metadata
    │  ← Parse complete WS message, extract t_exchange from payload
    │
    ├──→ File Writer (Parquet, batched by venue + time window)
    │
    └──→ Ticker Plant (ZMQ pub/sub fan-out)
              │
              ├──→ Consolidated Order Book Builder
              ├──→ Latency Analytics
              └──→ (future) ML / Anomaly Detection
```

### Design Decisions

- **No Redis, no database.** Per professor's direction. Record raw data straight to files, analyze later. This mirrors prop firm practice: minimize overhead between feed and disk.
- **Ticker plant fan-out.** Collector publishes to downstream consumers via ZMQ pub/sub (or similar). One subscriber writes to disk, another builds the consolidated book, another runs analytics. The collector doesn't care what consumers do.
- **C/C++ collector, Python downstream.** The collector must use `SO_TIMESTAMPING` to get hardware NIC timestamps and hook into the SSL layer for per-packet timing. Python cannot do this. Everything after the raw log (normalization, book building, analytics) is Python.
- **Parquet storage.** Columnar, compressed, fast to query with PyArrow/DuckDB. Files named `{venue}_{symbol}_{YYYYMMDD}_{HHmm}.parquet`.

### Important Note from Professor

A single websocket message may span multiple TCP packets. Each packet gets its own NIC hardware timestamp. The collector must record how many bytes arrived at each timestamp as metadata alongside the parsed JSON. This gives per-message arrival profiles: first byte time, last byte time, reassembly duration.

## 4. Infrastructure

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Regions | 5 AWS regions, one per venue | Binance: `ap-northeast-1` (Tokyo); Coinbase: `us-east-1` (N. Virginia); Kalshi: `us-east-2` (Ohio); Polymarket: `eu-west-2` (London); OKX: `ap-east-1` (Hong Kong). All chosen families are PTP-supported. See § 5 for rationale. |
| AZ | Default | AZ differences are sub-ms; exchange latencies are ms-scale. Not meaningful. |
| Instance | `m7g.medium` (current) | Smallest PTP-supported size in the m7g (Graviton) family, ~$30/month each. M7i.large is the alternate path if course infra is provisioned. PTP-supported families: M7i/R7i/M7a/R7a/M7g/R7g/I8g/I8ge. |
| OS | Amazon Linux 2023 | chrony + ENA PTP support built in. |
| ENA driver | ≥ 2.10.0 | Required for PTP hardware clock. |
| Clock | chrony with PHC0 | `refclock PHC /dev/ptp_ena poll 0 delay 0.000010 prefer` |
| Access | Apache Guacamole | Professor-provisioned web-based remote desktop. Need sudo. |

### PTP Setup Reference

```bash
# Enable PTP in ENA driver
echo "options ena phc_enable=1" | sudo tee /etc/modprobe.d/ena.conf
# Reboot required

# Verify PTP device
for file in /sys/class/ptp/*; do echo -n "$file: "; cat "$file/clock_name"; done
# Expected: ena-ptp-<PCI slot>

# Verify/create symlink
ls -l /dev/ptp*
# If missing:
echo "SUBSYSTEM==\"ptp\", ATTR{clock_name}==\"ena-ptp-*\", SYMLINK += \"ptp_ena\"" \
  | sudo tee -a /etc/udev/rules.d/53-ec2-network-interfaces.rules
sudo udevadm control --reload-rules && udevadm trigger

# Configure chrony
# Add to /etc/chrony.conf:
#   refclock PHC /dev/ptp_ena poll 0 delay 0.000010 prefer
sudo systemctl restart chronyd

# Verify
chronyc sources
# Expected: #* PHC0  0  0  377  ...

# Verify SO_TIMESTAMPING support
ethtool -T enX0
```

## 5. Exchanges

| Venue | Type | Collector AWS Region | Auth for Market Data | L2 WS Feed | Notes |
|-------|------|----------------------|---------------------|------------|-------|
| Binance (global) | Crypto | `ap-northeast-1` (Tokyo) | No | Yes | Matching engine in Tokyo (Group 11). Use `data-stream.binance.vision` mirror; primary host geo-blocked from US |
| Coinbase | Crypto | `us-east-1` (N. Virginia) | No | Yes | AWS-native, confirmed |
| OKX | Crypto | `ap-east-1` (Hong Kong) | No (public feeds) | Yes | OKX runs on Alibaba Cloud HK (non-AWS-native); ap-east-1 is "near but not co-located", the most interesting non-AWS data point |
| Kalshi | Prediction | `us-east-2` (Ohio) | Likely yes | REST + WS hybrid | Closest AWS region to Chicago metro |
| Polymarket | Prediction | `eu-west-2` (London) | TBD | CLOB WS API | London vantage point |

**Primary instrument**: BTC/USD (or equivalent pair) across crypto venues.
**Prediction market instruments**: TBD.

### Binance Notes

- Matching engine confirmed Tokyo (ap-northeast-1a per Group 11 testing).
- From us-east-1, expect ~70-100ms latency vs ~3-5ms for Coinbase. This is a feature of the analysis, not a problem.
- **Endpoint**: `wss://data-stream.binance.vision/stream?streams=btcusdt@depth@100ms/btcusdt@trade`. Dual-stream combined subscription. Empirical observation 2026-05-08: the unbatched `@depth` stream actually flushes at ~1 Hz at the WebSocket layer with ~130 matching-engine events bundled per frame, so it does *not* preserve sub-second cadence (this overturned ADR-0006). `@depth@100ms` gives 10x finer WS-layer cadence for orderbook reconstruction; `@trade` carries the per-event matching-engine timestamp (`T` field) that depth events do not. Together they recover what `@depth` alone cannot. See ADR-0010.
- The primary host `wss://stream.binance.com:9443` returns HTTP 451 from US IPs (regulatory geo-block). The `data-stream.binance.vision` mirror is Binance's documented public-data-only host and is accessible from US. Re-verify mirror access from us-east-1 when the VM is provisioned.

## 6. Data Schema

### Per-Message Record

| Field | Type | Source |
|-------|------|--------|
| venue | string | collector config |
| symbol | string | parsed from payload |
| msg_type | enum | snapshot / delta |
| seq_num | uint64 | from exchange payload |
| t_exchange | uint64 (ns) | from exchange payload (exchange's self-reported timestamp) |
| t_nic_first | uint64 (ns) | HW NIC timestamp of first TCP packet of WS message |
| t_nic_last | uint64 (ns) | HW NIC timestamp of last TCP packet |
| t_userspace | uint64 (ns) | clock_gettime(CLOCK_REALTIME) after parse completes |
| packet_metadata | array[(hw_ts, byte_count)] | per-packet arrival info |
| bids | array[(price, size)] | L2 bid levels |
| asks | array[(price, size)] | L2 ask levels |

### Key Deltas

- `t_nic_first - t_exchange` → total observed feed latency (network + exchange internal processing). Cannot decompose further, but the distribution over time and comparison across venues is the value.
- `t_nic_last - t_nic_first` → message reassembly duration (multi-packet WS messages).
- `t_userspace - t_nic_last` → software processing overhead (kernel + application).
- Cross-venue `t_nic_first` comparison → which feed is actually faster from our vantage point.

### What We're NOT Measuring

- We cannot decompose `t_nic_first - t_exchange` into network vs exchange processing — it's a single opaque value.
- We cannot verify exchange timestamps are accurate — we can only measure consistency.
- Absolute numbers depend on our vantage point (us-east-1). Different region = different results. We state our vantage point and the measurement is valid from that location.
- **Sub-frame event timing on `@depth@100ms` is structurally inaccessible.** The depth stream collapses every matching-engine event that occurred during a flush window into a single timestamp per WS frame (~10 events bundled per 100ms flush at typical BTCUSDT cadence, more during volatility). The parallel `@trade` subscription recovers per-event timing via the `T` field, but only for executed trades, not order book updates. Empirical 2026-05-08 evidence in ADR-0010 motivates the dual-stream design; this limitation is its honest framing.

## 7. Order Book Depth: L2

- **L1** (best bid/ask): too shallow for consolidated book analysis.
- **L2** (aggregated price levels): correct depth. Enough to merge price ladders across venues and see where real liquidity sits.
- **L3** (individual orders): most exchanges don't offer publicly. Data volume too high for semester project.

L2 snapshots + incremental deltas via websocket is the standard approach across all target venues.

## 8. Consolidated Order Book

Merge L2 books from all crypto venues into a unified view of BTC/USD liquidity. Key analyses:

- **Staleness thresholds**: How does the consolidated BBO change at 5ms / 10ms / 50ms staleness windows?
- **Best execution analysis**: How often does the true best bid/ask live on a slower feed that you'd miss with a tight staleness cutoff?
- **Volatility correlation**: Do feeds degrade (higher latency, more variance) during high-volatility events?
- **Cross-market timing** (stretch goal): Does a crypto move on Coinbase lead or lag a related Polymarket prediction market contract?

## 9. Prior Art

### Group 04 — Fall 2025 (Bybit PTP HW Timestamping)

Single-exchange C++ collector with SO_TIMESTAMPING. Custom `TimestampAwareStream` wrapping SSL layer. Measured wire-to-read latency, SSL decryption overhead, exchange latency. Binary logging. Bybit only, no cross-exchange, no consolidated book, no ticker plant.

**Relevance to us**: Technical reference for implementing NIC-level HW timestamping in C++.

### Group 08 — Fall 2024 (Kalshi Ticker Plant)

Java/Aeron ESB architecture. Kalshi WS client → data processor → ticker plant → subscribers (including Redshift recorder). Maintained live order books, generated top-of-book messages. No PTP, no HW timestamping.

**Relevance to us**: Architectural reference for ticker plant pattern and order book maintenance pipeline.

### Group 11 — Spring 2024 (Binance Latency Optimization)

Optimized trading API round-trip latency to Binance from Tokyo AZs. Confirmed Binance in ap-northeast-1a. System tuning (busy_poll, C-states, IRQ pinning). TCP keep-alive reduced latency from 55ms to ~10ms. No PTP, no market data recording, no cross-exchange analysis.

**Relevance to us**: Confirmed Binance Tokyo location. System tuning techniques to reference (not implement) in writeup.

### Our Contribution

We combine Group 04's HW timestamping approach with Group 08's ticker plant architecture, extend to multiple exchanges, and add the consolidated order book as the core analytical deliverable. The cross-venue timing analysis enabled by PTP is the novel contribution.

## 10. Deliverables

1. **Per-venue feed latency distributions** — mean, variance, P50/P99/P999, time-of-day patterns, volatility correlation.
2. **Consolidated order book reconstruction** — merged BBO across venues with staleness analysis.
3. **Packet-level metadata analysis** — message reassembly times, multi-packet WS message characterization.
4. **GitLab repository** — all code, configs, docs, analysis notebooks.

## 11. Open Questions

- [ ] AI/ML component — what does the professor expect? Candidates: anomaly detection on consolidated book, latency prediction, NLP query interface over recorded data.
- [ ] Real-time consolidated book vs batch reconstruction — real-time is significantly more engineering work.
- [ ] Exact prediction market instruments to track.
- [ ] Team task split across four members.
- [ ] Professor VM provisioning timeline and Guacamole access.

## 12. What We Can Do Before VMs Are Ready

On a temporary t3.micro (no PTP, placeholder timestamps):

1. Write websocket collectors for all five exchanges — connect, parse L2, extract t_exchange, log to stdout.
2. Define Parquet schema and build the writer with PyArrow.
3. Build ticker plant fan-out with ZMQ pub/sub.
4. Build consolidated order book merge logic with staleness thresholds.
5. Research SO_TIMESTAMPING implementation in C++ — this is the hardest part and the longest lead time.

Items 1–4 are fully portable to the real instance. Item 5 is the research spike that should start immediately.
