# Roadmap: aws-ptp-crypto-recording

**Created:** 2026-04-20
**Last updated:** 2026-05-08 (Kraken→OKX swap, Binance dual-stream, PTP-vs-NTP descoped per ADR-0011)
**Depth:** quick (3-5 phases, 1-3 plans each)
**Coverage:** 33 / 33 v1 requirements mapped

---

## Phase 1: Local end-to-end with Binance (laptop only, no cloud spend)

**Goal:** Establish the full migration-friendly architecture (TimestampSource, RecordSink, config loader) end-to-end with one venue (Binance) on a laptop. Proves the abstraction stack works before fanning out to more venues. Zero infra cost.

**Requirements:** ARCH-01, ARCH-02, ARCH-05, COLLECT-03, COLLECT-06, STORE-01, STORE-02, STORE-03

**Success criteria:**

1. Repo scaffold matches CLAUDE.md repo conventions: `collector/`, `collector/timestamp/`, `sinks/`, `pipeline/`, `pipeline/sources/`, `analysis/`, `infra/`, `config/`, `tests/`, `data/` (gitignored).
2. `TimestampSource` abstract interface defined; `ClockGettimeSource` returns plausible timestamps for laptop runs.
3. `RecordSink` abstract interface defined; `LocalParquetSink` writes batched messages to `./data/{venue}/{YYYY-MM-DD}/{HH}.parquet`.
4. `RECORDING_CONFIG=local` env var loads `config/recording.local.yaml`; collector wires the timestamp source and sink from that config (no hardcoded paths).
5. Binance collector connects to `data-stream.binance.vision` combined-stream (`@depth@100ms` + `@trade`, per ADR-0010), parses messages, attaches timestamps, writes Parquet for at least 60 minutes without crashes or parser errors.

**Plans (suggested):**
- `repo-scaffold-and-abstractions`: directory layout, base interfaces, config loader, gitignore tuning
- `binance-collector-end-to-end`: WS connect, parse, timestamp attach, Parquet write

---

## Phase 2: Remaining venues + lab-tier pipeline (still laptop-only)

**Goal:** Bring all five venues online and add the lab-tier components (validator, book builder, consolidated book) reading from local Parquet. Closes the loop on the two-tier architecture in a single-machine setting before cloud deployment.

**Requirements:** ARCH-03, COLLECT-01, COLLECT-02, COLLECT-04, COLLECT-05, BOOK-01, BOOK-02, BOOK-03, LAB-01, ANAL-01

**Success criteria:**

1. All five venues (Coinbase, OKX, Binance, Kalshi, Polymarket per ADR-0009) connect concurrently and write to per-venue Parquet files for a 60-minute capture without parser errors.
2. `RecordSource` abstract interface defined; `LocalParquetSource` iterates messages from `./data/`.
3. Validator detects and logs `seq_num` gaps per venue.
4. Per-venue L2 book reconstruction works (snapshot plus diff handshake) and matches partial-depth-stream snapshots when they exist.
5. Cross-venue consolidated BBO computed at 5/10/50 ms staleness windows.
6. Preliminary latency-distribution notebook (mean, stdev, P50, P99, P999 per venue) using laptop `clock_gettime` timestamps.

**Plans (suggested):**
- `crypto-venues-coinbase-okx`: pattern matches Binance collector, different parsers
- `prediction-venues-kalshi-polymarket`: WS handshake variations; Kalshi may need REST plus WS hybrid
- `lab-pipeline-prototype`: validator plus book_builder plus consolidated_book all reading via LocalParquetSource

---

## Phase 3: Cloud deployment + S3 + PTP infrastructure

**Goal:** Deploy collectors to AWS in correct regions with PTP synchronization and S3 storage. The migration is a config flip from `local` to `aws`, validating the migration-friendly architecture in practice. Initial deployment uses personal `m7g.medium` instances for smoke testing; final deployment uses course-provided `M7i.large` with the same script and config schema.

**Requirements:** ARCH-04, STORE-04, TIME-01, TIME-02, LAB-02

**Success criteria:**

1. `S3ParquetSink` writes Parquet shards to `s3://{bucket}/{venue}/{YYYY-MM-DD}/{HH}.parquet`.
2. `S3ParquetSource` reads the same with boto3 for downstream lab consumption.
3. EC2 instances launched in 5 regions (per ADR-0009: ap-northeast-1, us-east-1, us-east-2, eu-west-2, ap-east-1) with Amazon Linux 2023, ENA driver >= 2.10.0, PHC enabled.
4. `chronyc sources` shows PHC0 as selected reference with stable sync error; `clock_gettime(CLOCK_REALTIME)` is now PTP-disciplined.
5. `infra/instance-setup.sh` is idempotent and works for personal `m7g.medium` and official `M7i.large` with no script changes (only IAM credentials and bucket names differ).
6. Lab-tier pipeline runs on a separate machine (laptop or second EC2) and pulls via `S3ParquetSource` without re-running collectors.
7. `RECORDING_CONFIG` flips from `local` to `aws` cleanly with no code changes.

**Plans (suggested):**
- `s3-sink-and-source`: boto3 wrapping, batch upload, source iteration
- `ec2-ptp-bootstrap`: provisioning script, chrony config, PHC0 setup, ENA driver verification (works on m7g and m7i)
- `lab-tier-on-separate-machine`: validator plus book_builder consuming from S3ParquetSource

**Pragmatic note:** Phase 3 can begin on personal `m7g.medium` (~$30/month per instance) before the official infrastructure is provisioned. The architecture is identical; only the IAM credentials and bucket names differ.

---

## Phase 4: PTP HW timestamps (C++) + ticker plant + final analytics

**Goal:** Replace the Python timestamp source with a C++ collector using SO_TIMESTAMPING for NIC-level hardware timestamps. Add ZMQ ticker plant for live fan-out. Produce the final analytical deliverables.

**Requirements:** COLLECT-07, COLLECT-08, TIME-03, TICKER-01, TICKER-02, TICKER-03, ANAL-02, ANAL-04

**Success criteria:**

1. C++ collector connects to one venue (Coinbase first) using Boost.Asio and Boost.Beast over TLS.
2. Per-packet NIC HW timestamps captured via `SO_TIMESTAMPING` and `recvmsg` control messages.
3. Multi-packet message reassembly metadata `(hw_ts, byte_count)` tuples recorded with each parsed message.
4. Collector publishes via ZMQ pub/sub; two subscribers consume concurrently without drops over a 1-hour run.
5. Time-of-day latency patterns and volatility-correlation overlay produced.
6. Per-message reassembly-duration analysis produced from `(hw_ts, byte_count)` metadata.

**Plans (suggested):**
- `cpp-collector-coinbase`: project layout, Boost.Asio/Beast, SSL connect, JSON parser
- `so-timestamping-and-zmq`: `recvmsg` control messages, per-packet metadata, ZMQ pub/sub
- `final-analytics-and-comparisons`: time-of-day, volatility correlation, reassembly notebooks (PTP-vs-NTP descoped per ADR-0011)

---

## Coverage Summary

| Phase | Requirements | Count |
|---|---|---|
| Phase 1 | ARCH-01, ARCH-02, ARCH-05, COLLECT-03, COLLECT-06, STORE-01..03 | 8 |
| Phase 2 | ARCH-03, COLLECT-01, COLLECT-02, COLLECT-04, COLLECT-05, BOOK-01..03, LAB-01, ANAL-01 | 10 |
| Phase 3 | ARCH-04, STORE-04, TIME-01, TIME-02, LAB-02 | 5 |
| Phase 4 | COLLECT-07, COLLECT-08, TIME-03, TICKER-01..03, ANAL-02, ANAL-04 | 8 |

31 v1 requirements / 31 mapped / 0 unmapped (TIME-04 and ANAL-03 dropped per ADR-0011).

---
*Last updated: 2026-05-08 after ADR-0009 (5-region), ADR-0010 (Binance dual-stream), ADR-0011 (PTP-vs-NTP descope)*
