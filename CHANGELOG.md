# Changelog

All notable changes to this project, in reverse chronological order. Format follows [Keep a Changelog](https://keepachangelog.com/) with custom sections (`Decided`, `Researched`, `Pivoted`) for the academic context.

## [Unreleased]

Work in progress. Phase 1 plan `binance-collector-end-to-end` is the next quick task.

---

## [2026-05-16] P2 deployed: NIC hardware timestamps verified on Tokyo

The Python wsproto + `ssl.MemoryBIO` raw-socket path is production-verified on the Tokyo box: NIC hardware timestamps on 100% of `binance_nic` records (`btcusdt` + `ethusdt` across `@depth@100ms` + `@trade`), userspace jitter p50 153 µs (depth) to 1.0 ms (trade), running alongside the untouched `binance` PTP-userspace baseline. Evidence: [docs/status_snapshot_2026-05-16.md](docs/status_snapshot_2026-05-16.md).

### Researched

- AWS Nitro / ENA ships RX hardware timestamping disabled; `SO_TIMESTAMPING` on the socket is necessary but not sufficient. The `SIOCSHWTSTAMP` ioctl (`HWTSTAMP_FILTER_ALL`) must flip device-level RX config `0 → 1`. Undocumented by AWS for the Python `recvmsg` path; automated via `infra/scripts/enable-hw-timestamping.sh` (systemd `ExecStartPre`). See [ADR-0012](docs/decisions/0012-p2-path-selection.md) "Deployment addendum".

### Pivoted

- ADR-0005 ("Python prototype before C++ HW timestamps") status → **Superseded by [ADR-0012](docs/decisions/0012-p2-path-selection.md)**. Its premise that C++ would be required for NIC hardware timestamps is empirically dead; the Python path produces nanosecond hardware stamps on production.

### Changed

- `UPDATE.md` §0, `CLAUDE.md` Key Context, `infra/README.md`, `docs/final_writeup_outline.md` §3a updated; status snapshot renamed to `docs/status_snapshot_2026-05-16.md`. Detail lives in those docs and ADR-0012; not restated here.

---

## [2026-05-08] Drop PTP-vs-NTP comparison from v1; reframe production instance as `m7g.medium`

### Decided

- **ADR-0011: Drop PTP-vs-NTP comparison from v1 deliverables.** The comparison is not on the critical path for the cross-venue latency analysis. Producing it properly requires either parallel NTP-only infra per region or shared-host complexity. Cleaner to drop the deliverable, prune the schema field, and let spec, code, and CLAUDE.md tell the same story.

### Changed

- `collector/timestamp/base.py`: removed `t_ntp` field from `Timestamps` dataclass
- `collector/timestamp/clock_gettime_source.py`, `collector/timestamp/ptp_source.py`: removed `t_ntp=ns` from `capture()`
- `docs/proposal.md` § 6 schema, § 6 Key Deltas, § 8, § 10 deliverable #3 updated to drop PTP-vs-NTP commitments
- `UPDATE.md` § 1 schema and "Are measuring" list updated
- `README.md` architecture diagram updated (dropped "PTP vs NTP" from analytics block)
- `CLAUDE.md`, `README.md`, `UPDATE.md`, `docs/proposal.md` § 4 reframed deployment target: `m7g.medium` (~$30/month each, smallest PTP-supported size in m7g family) is the named production instance across all 5 regions; `M7i.large` is the alternate path if course infra is provisioned. ADR-0008's "smoke test before official infra" framing is unchanged (immutable); formal supersession deferred until team confirms `m7g.medium` is the permanent answer.

---

## [2026-05-08] Binance dual-stream pivot

Empirical observation invalidated ADR-0006's premise.

### Researched

- The unbatched `@depth` stream on `wss://data-stream.binance.vision` flushes at roughly 1 Hz at the WebSocket layer, with on the order of 130 matching-engine events bundled per WS frame. The frame-level arrival timestamp therefore preserves no more sub-second cadence than `@depth@100ms` would.
- Per-event matching-engine timestamps (`T` field) are not present on `depthUpdate` events but are present on every individual `trade` event from `@trade`.

### Decided

- ADR-0010: Switch Binance subscription from unbatched `@depth` to a combined-stream subscription of `@depth@100ms` + `@trade`. The depth stream gives 10x finer WS-layer cadence (10 Hz vs 1 Hz) for orderbook reconstruction; `@trade` carries the per-event matching-engine `T` for downstream latency decomposition.

### Changed

- `collector/exchanges/binance.py`: rewritten to subscribe via combined-stream URL and dispatch parsing on the `stream` wrapper field
- `config/exchanges.yaml`: removed the YAML-tunable `stream:` field on the binance entry; the dual-stream subscription is the measurement contract and is hardcoded in `BinanceCollector.run()`
- `docs/proposal.md` § 5 Binance Notes block updated to reflect dual-stream
- `UPDATE.md` § 4 step 2 updated to reflect dual-stream
- ADR-0006 status updated to "Superseded by ADR-0010"

---

## [2026-05-08] Scope change: Kraken to OKX, true 5-region layout

### Decided

- Replace Kraken with OKX as one of the five target venues. OKX is a top-3 global exchange by volume and runs on Alibaba Cloud Hong Kong (non-AWS-native). ap-east-1 gives a "near but not co-located" vantage point, the most interesting non-AWS data point in the cross-venue latency analysis.
- Adopt a true 5-region AWS layout, one venue per region, replacing the original "us-east-1 covers everything except Binance" framing:
  - Binance Global → `ap-northeast-1` (Tokyo)
  - Coinbase Spot → `us-east-1` (N. Virginia)
  - Kalshi → `us-east-2` (Ohio, closest to Chicago metro)
  - Polymarket → `eu-west-2` (London)
  - OKX → `ap-east-1` (Hong Kong, near OKX's Alibaba Cloud HK matching engine)

Supersedes the regional layout in ADR-0003. Cross-region timestamp validity is unchanged (all AWS regions share the same atomic clock fleet); only the *which* regions changed, not the methodology.

### Changed

- `config/exchanges.yaml`: removed `kraken` entry, added `okx` entry, set explicit region for all five venues
- `collector/exchanges/kraken.py` → `collector/exchanges/okx.py` (skeleton, NotImplementedError; `OKXCollector` class)
- `collector/exchanges/__init__.py` `EXCHANGES` registry: kraken to okx
- `docs/proposal.md` § 4 (Infrastructure) and § 5 (Exchanges) updated for 5-region layout and venue swap
- `CLAUDE.md`, `README.md`, `UPDATE.md`: multi-region tables and venue lists updated

---

## [2026-04-29] Phase 1 scaffold complete

Quick task 1: scaffold repo and abstractions.

### Added

- Directory structure: `collector/`, `collector/timestamp/`, `sinks/`, `pipeline/`, `pipeline/sources/`, `tests/`, `config/`
- Abstract interfaces: `TimestampSource`, `RecordSink`, `RecordSource`, `Collector` (all in `*/base*.py`)
- `Timestamps` dataclass mirroring proposal § 6 schema
- Concrete `ClockGettimeSource` (working, smoke-tested)
- Concrete `PTPClockGettimeSource` (subclass marker for PTP-disciplined regime)
- Stub `NICHwTimestampSource` (raises NotImplementedError until C++ collector exists)
- Skeleton `LocalParquetSink`, `LocalParquetSource` (method shapes stable; bodies are next quick task)
- Stub `S3ParquetSink`, `S3ParquetSource` (raise NotImplementedError until Phase 3)
- `collector/config_loader.py` with `load_config()` and `load_exchanges()` keyed on `RECORDING_CONFIG` env var
- YAML configs: `config/exchanges.yaml`, `config/recording.local.yaml`, `config/recording.aws.yaml`
- `requirements.txt` capturing current and near-future Python deps
- ADR-0001 through ADR-0008 (retroactive, capturing decisions to date)
- `README.md` replacing GitLab boilerplate
- `CHANGELOG.md` (this file)
- `docs/decisions/` directory with ADR template and index
- `docs/weekly-reports/` directory with template

### Decided

- ADR-0008: Use personal `m7g.medium` for cloud smoke testing before official infra arrives

---

## [2026-04-28] Architecture pivot adopted (UPDATE.md)

Significant pivot following research and professor feedback. New architecture: two-tier (cloud collectors + lab pipeline), multi-region (us-east-1 + ap-northeast-1), three abstractions (TimestampSource, RecordSink, RecordSource) for migration-friendly deployment, pragmatic Python-first build order with C++ deferred to where SO_TIMESTAMPING actually requires it.

### Added

- `UPDATE.md` (living architecture-of-record)
- Re-phased `.planning/ROADMAP.md` from collector / infra / C++ / analytics to local-EE / venues+lab / cloud-deploy / C+++final-analytics, matching UPDATE.md's build order
- Architecture and Lab requirement categories in `.planning/REQUIREMENTS.md` (added 7 reqs; total 33 v1)
- ADR-0002 through ADR-0007 retroactively documenting the pivot

### Changed

- `CLAUDE.md` rewritten to reflect new architecture
- `.planning/PROJECT.md` updated with two-tier and multi-region context

### Decided

- ADR-0002: Two-tier architecture per professor (cloud collectors + lab pipeline)
- ADR-0003: Multi-region collector deployment (us-east-1 for Coinbase / Kraken / Kalshi / Polymarket; ap-northeast-1 for Binance)
- ADR-0004: Three abstractions (TimestampSource, RecordSink, RecordSource) for laptop-to-cloud migration as a config flip
- ADR-0005: Python asyncio prototype before C++ HW timestamps; C++ replaces only the timestamp-acquisition layer
- ADR-0006: Use unbatched `@depth` not `@depth@100ms` (preserves sub-100ms temporal resolution)
- ADR-0007: GSD with `quick` mode for lighter planning workflow

### Pivoted

- Original 4-phase roadmap (collector → infra → C++ → analytics) superseded by new 4-phase ordering (local-EE → venues+lab → cloud-deploy → C+++final-analytics) per UPDATE.md's "build everything portable first, swap implementations later" principle.

---

## [2026-04-20] Initial planning and Binance research

GSD project initialization, plus empirical research on Binance market-data access from US IPs.

### Added

- `CLAUDE.md` project conventions
- `docs/proposal.md` (full architecture spec, 12 sections)
- `docs/questions.md` (open prof questions tracker)
- `.gitignore`
- `.planning/PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`, `config.json` (initial GSD state)
- `analysis/binance_data_stream_explore.ipynb` (latency-measurement methodology validation)
- Initial commit `850cd02 Initial Planning`

### Researched

- Binance market-data WS access from US IPs:
  - `wss://stream.binance.com:9443` returns HTTP 451 (RFC 7725 "Unavailable For Legal Reasons") from US residential IP — confirmed for both `@depth` (L2) and `@bookTicker` (L1) endpoints
  - `wss://data-stream.binance.vision` works from same IP and delivers canonical `depthUpdate` payloads
  - DNS analysis: both hosts resolve to AWS `ap-northeast-1` (Tokyo) IP space; no CDN; same-region fan-out architecture; no documented latency differential between the two hosts
  - All Binance Spot pair tiers (top-cap, mid-cap, lower-cap, crypto-cross, stablecoin-cross, fiat-quote) are accessible via the `.vision` mirror; coverage is uniform
- Latency-measurement methodology: `E - local_receive` deltas as a sanity-check baseline before PTP infrastructure is online
- TCP/TLS handshake timing comparison: `data-stream.binance.vision` and `stream.binance.com` are statistically indistinguishable from same vantage point (~170-200ms TCP, ~330-430ms TLS)

### Decided

- ADR-0001: Use `data-stream.binance.vision` as Binance endpoint (US geo-block on `.com` host)

### GitLab access

- User `@yichen32` SSH key registered on gitlab.engr.illinois.edu (auth verified)
- Read access to `group_19_project` granted via course-group inheritance (Reporter role)
- **Push access pending**: Maintainer/Owner on the team subgroup or project must add `@yichen32` as Developer or Maintainer for `git push` to succeed

---

## [2026-04-20] Repo creation

Initial commit by course staff; project bootstrapped on gitlab.engr.illinois.edu.

---

*Format: changes are grouped by date in reverse chronological order. Sections: Added (new), Changed (modified), Removed (deleted), Decided (ADR shipped), Researched (empirical findings), Pivoted (course-correction with reason).*
