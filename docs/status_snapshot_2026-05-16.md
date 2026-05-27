# Project Status Snapshot — 2026-05-16

**For:** Professor Lariviere / graders. One-page "if grades were due
tomorrow" summary. Every claim is cross-referenced to evidence in the repo.

**Project:** aws-ptp-crypto-recording — PTP-synchronized cross-exchange
market data recording pipeline. Group 19, IE421 Spring 2026.

---

## Where the project stands

A PTP-synchronized recording pipeline is **deployed and recording in
production** on the first venue/region, with **NIC hardware timestamps
confirmed working** — the headline deliverable is met, not future work.
Two collectors run side by side on Tokyo: the PTP-disciplined userspace
baseline (`binance`) and the NIC-hardware-timestamp path (`binance_nic`).
The architecture, the 5-venue collector framework, the migration-friendly
abstractions, and the lab-side validation tooling are complete.

## What is deployed and recording

- **AWS `ap-northeast-1` (Tokyo)** runs two systemd services
  (`Restart=on-failure`, `RECORDING_CONFIG=aws`):
  - `group19-collector@binance` — `PTPClockGettimeSource` (userspace
    PTP-disciplined baseline), untouched since P1.
  - `group19-collector@binance_nic` — NIC hardware timestamps via the
    wsproto + `ssl.MemoryBIO` raw-socket path (ADR-0012).
- Subscribed: `btcusdt`+`ethusdt`, each `@depth@100ms` + `@trade` (combined
  stream on `data-stream.binance.vision`).
- Output: Parquet to `./data/{binance,binance_nic}/<date>/`, synced to
  `s3://group19-ptp-tokyo/` every 5 min via cron.
- Evidence: [infra/README.md](../infra/README.md),
  [collector/transport/raw_ws.py](../collector/transport/raw_ws.py),
  [collector/exchanges/binance_nic.py](../collector/exchanges/binance_nic.py).

## What is built and deploy-ready (awaiting regional EC2)

- **`coinbase_nic`** (→ `us-east-1`, bucket `group19-ptp-virginia`) and
  **`okx_nic`** (→ `ap-east-1`, bucket `group19-ptp-hong-kong`) NIC-
  timestamped collectors, built 2026-05-16. Same subclass-and-override-
  `run()` pattern as `binance_nic`
  ([collector/exchanges/coinbase_nic.py](../collector/exchanges/coinbase_nic.py),
  [collector/exchanges/okx_nic.py](../collector/exchanges/okx_nic.py)):
  override `run()` only, inherit `parse()`, registered in `EXCHANGES`.
  `RawWebSocketClient.send()` added for post-handshake subscription.
- Deploy procedure: [infra/README.md](../infra/README.md) "Deploying
  additional regions". The systemd template and `install.sh` are venue-
  agnostic; no per-venue code changes are needed to bring these up once
  the EC2 boxes exist.
- **SIOCSHWTSTAMP wiring committed and region-portable (2026-05-18):** the
  `ExecStartPre` line and `infra/scripts/enable-hw-timestamping.sh`
  previously lived only on the Tokyo box (flagged 2026-05-16, committed
  2026-05-17) and now match the running Tokyo unit. The script no longer
  hardcodes `ens5`: with no argument (how the unit invokes it) it
  auto-detects the active ENA interface (first non-loopback UP link),
  accepts an explicit interface arg as an override, and falls back to
  `ens5` only if detection yields nothing. A fresh region self-configures
  via git clone + `install.sh` with no per-box interface check; the only
  post-deploy step is confirming RX timestamping is on after first start.

## Sample numbers from Tokyo

| Metric | Value | Meaning |
|---|---|---|
| `chronyc tracking` Reference ID | `PHC0` | chrony locked to the NIC PTP hardware clock |
| chrony RMS offset | sub-microsecond | clock discipline quality |
| `binance` `delta_ns` median | 1.4 - 4.4 ms | exchange-stamp → local-PTP-stamp gap (userspace baseline) |
| `binance_nic` NIC timestamp coverage | **100% of records** | hardware stamp populated, not the 0 sentinel |
| `binance_nic` userspace jitter p50 | 153 µs (depth) - 1.0 ms (trade) | `t_ptp_ns - t_nic_first_ns`: software overhead above the NIC stamp |
| `binance_nic` userspace jitter p99 | 1.4 ms (depth) - 30 ms (trade) | trade tail = asyncio scheduling under burst |
| `binance_nic` avg chunks/msg | 1.01 - 1.20 | per-message reassembly attribution healthy |

The userspace-jitter numbers are the core result: they quantify exactly how
much measurement noise the PTP-disciplined-userspace baseline carries that
the NIC hardware path removes.

## Complete / partial / future

### Complete

- PTP infrastructure operational (chrony + PHC0, verified)
- **NIC hardware timestamps deployed and verified on Tokyo (2026-05-16)** —
  Python wsproto + `ssl.MemoryBIO` path, 100% record coverage
  ([ADR-0012](decisions/0012-p2-path-selection.md))
- Migration-friendly architecture: `TimestampSource` / `RecordSink` /
  `RecordSource` abstractions, config-driven ([ADR-0004](decisions/0004-three-abstractions-for-migration.md))
- 5-venue collector framework, uniform Parquet schema
  ([collector/exchanges/](../collector/exchanges/))
- Binance collector v1 with empirically-validated dual-stream subscription
  ([ADR-0010](decisions/0010-binance-dual-stream-depth-100ms-plus-trade.md))
- Tokyo deployment: systemd units, S3 sync cron, HW-timestamp enable
  script, deploy scripts ([infra/](../infra/))
- Lab-side sequence-gap validator ([tools/lab_validator.py](../tools/lab_validator.py))
- Analysis + cross-venue tooling scaffolded ([tools/](../tools/))
- 12 ADRs documenting every significant decision and pivot
  ([docs/decisions/](decisions/))

### Partial

- Coinbase + OKX collectors implemented, plus `coinbase_nic` / `okx_nic`
  NIC-timestamped variants built and deploy-ready 2026-05-16; not yet
  deployed (await second-region provisioning). See "What is built and
  deploy-ready" above.
- Kalshi collector: RSA-PSS auth flow scaffolded, blocked on API keys
  ([collector/exchanges/kalshi.py](../collector/exchanges/kalshi.py))
- Polymarket collector: public feed implemented, 500-asset cap handled
- Cross-venue latency analysis: per-venue stats work; cross-venue matching
  is stubbed pending multi-region data

### Future work

- Production `binance` vs `binance_nic` comparison analysis (PTP-userspace
  vs NIC-hardware jitter) — the ADR-0012 writeup payload, data now flowing
- Additional region deployments (Coinbase/Virginia next for cross-venue)
- Real-time consolidated cross-venue book service
- ML / anomaly detection layer

## Key research findings so far

1. **The `@depth` coalescing finding.** Binance's "unbatched" `@depth`
   stream flushes ~1 Hz with ~130 matching-engine events bundled per WS
   frame, so it preserves no more sub-second cadence than `@depth@100ms`.
   This overturned [ADR-0006](decisions/0006-unbatched-depth-stream.md) and
   drove the dual-stream design in
   [ADR-0010](decisions/0010-binance-dual-stream-depth-100ms-plus-trade.md).
2. **The ctypes microbenchmark finding.** A ctypes `clock_gettime` call is
   ~1.8 µs, measurably slower than `time.time_ns()`; "closer to the syscall"
   was the wrong intuition. Documented in
   [collector/timestamp/ptp_source.py](../collector/timestamp/ptp_source.py).
3. **The Q7 buffering finding.** The Python `websockets` library buffers
   ahead of the kernel socket, so external `recvmsg` cannot read
   SCM_TIMESTAMPING ancillary data. This drove the wsproto + `MemoryBIO`
   raw-socket path in [ADR-0012](decisions/0012-p2-path-selection.md).
4. **The AWS Nitro SIOCSHWTSTAMP finding.** AWS Nitro / ENA ships RX
   hardware timestamping disabled; `SO_TIMESTAMPING` on the socket is
   necessary but not sufficient. The `SIOCSHWTSTAMP` ioctl
   (`HWTSTAMP_FILTER_ALL`) must flip device-level RX config `0 → 1`.
   Without it, `recvmsg` returns a zero hardware timestamp and silently
   degrades to software. AWS docs do not state this for the Python path.
   Automated via `infra/scripts/enable-hw-timestamping.sh` (systemd
   `ExecStartPre`). See ADR-0012 "Deployment addendum".

## Open questions

Tracked in [docs/questions.md](questions.md). Highlights: AWS budget /
provisioning timeline for additional regions, and prediction-market
instrument selection (blocks Kalshi/Polymarket symbol config).

## Timeline for completion

| Milestone | Status |
|---|---|
| P2 NIC-HW timestamp source (wsproto + MemoryBIO) | **Done, verified on Tokyo 2026-05-16** |
| Production vs binance_nic comparison analysis | Data flowing; analysis next |
| Second region deploy (Coinbase/Virginia) | ~1-2 days (collector ready) |
| Cross-venue analysis with real multi-region data | after 2+ regions live |
| Final writeup + presentation | outlines ready ([final_writeup_outline.md](final_writeup_outline.md), [presentation_outline.md](presentation_outline.md)); prose pending comparison data |

## Engineering-process evidence

Every pivot is a documented ADR with explicit supersession (0003→0009,
0006→0010, 0005→0012), not a silent rewrite. ADR-0012 carries a dated
deployment addendum capturing the AWS Nitro finding. The CHANGELOG is the
chronological view; [UPDATE.md](../UPDATE.md) is the architecture-of-record.
This is the auditable decision trail the ADR system exists to produce.
