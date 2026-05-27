# aws-ptp-crypto-recording

## What This Is

Semester-long IE421 group project measuring cross-exchange feed latency and consolidated order book staleness using PTP-synchronized hardware NIC timestamps. Two-tier architecture per professor: lean cloud-tier collectors record L2 order book data from five venues to S3, lab-tier pipeline pulls from S3 to validate, build books, and analyze. Full architecture in `UPDATE.md`; original proposal in `docs/proposal.md`.

## Core Value

Characterize feed latency and consolidated-book staleness with PTP-grade precision across five venues from five distinct AWS regions.

## Requirements

### Validated

(None yet. All v1 requirements are hypotheses until shipped.)

### Active

See `.planning/REQUIREMENTS.md` for the full v1 list across eight categories: Architecture, Collection, Storage, TickerPlant, Time, Book, Lab, Analytics. 33 requirements total.

### Out of Scope

- Trading execution (project is measurement and analysis, not trading)
- L3 order-by-order data (most venues do not offer publicly; volume too high for semester scope)
- Real-time consolidated book reconstruction (pending professor confirmation; defaulting to batch from Parquet files)
- AI/ML component (pending professor clarification on expected scope)
- Sub-millisecond accuracy on laptop-only measurements (only AWS PTP-synced clock counts for final numbers)
- Binance perpetual futures or options (different endpoint domains; separate US-access verification needed; not in scope)

## Context

Repo conventions, course rules, and tech stack live in `CLAUDE.md` at the repo root. Living architecture decisions live in `UPDATE.md`. Full technical specification in `docs/proposal.md`. Open questions awaiting professor input in `docs/questions.md`.

Architecture decisions:

- Two-tier separation per professor: cloud collectors are lean and write-only; lab tier handles validation, book building, and analysis.
- Multi-region cloud tier: 5 distinct AWS regions, one venue per region (per ADR-0009). Binance `ap-northeast-1`, Coinbase `us-east-1`, Kalshi `us-east-2`, Polymarket `eu-west-2`, OKX `ap-east-1`. Cross-region timestamps valid because all AWS regions reference the same atomic clock fleet.
- Three abstractions enable laptop-to-cloud migration as a config change: `TimestampSource`, `RecordSink`, `RecordSource`. All selected via `RECORDING_CONFIG` env var.
- Pragmatic build order: Python asyncio prototype first using `clock_gettime` placeholder; C++ collector replaces only the timestamp-acquisition layer once SO_TIMESTAMPING precision matters. Schema is identical.

Empirical findings:

- Binance access from US IPs requires `wss://data-stream.binance.vision` (the `.com` host returns HTTP 451). Verified 2026-04-20 from US residential IP. Re-verify from `us-east-1` once VMs are provisioned.
- All Binance Spot trading pairs (top-cap, mid-cap, lower-cap, crypto-cross, stablecoin-cross, fiat-quote) are accessible via the `.vision` mirror. Coverage is uniform.
- Latency-measurement methodology validated in `analysis/binance_data_stream_explore.ipynb` using `E - local_receive` deltas as a sanity check before PTP infrastructure is online.

## Constraints

- **Tech stack**: Python asyncio for collectors and pipeline; C/C++ (Boost.Asio/Beast) for SO_TIMESTAMPING when needed. Pragmatic split: Python first everywhere, C++ where Python cannot reach kernel-level timestamping.
- **Infra**: AWS EC2 `m7g.medium` (Graviton, smallest PTP-supported size, ~$30/month each), Amazon Linux 2023, chrony with PHC0. Production target is personal `m7g.medium` × 5 regions; M7i.large is the alternate if course infra is provisioned. Lab tier on Apache Guacamole VM.
- **Course rules**: Daily commits to GitLab. Individual attribution per commit. Communication on Discord and recorded weekly Zoom only. English only. Team leader submits weekly reports to Canvas + Box.
- **Schedule**: Semester-long. Deliverables due before semester end.
- **GitLab access**: User `@yichen32` currently has Reporter (read-only) on `group_19_project`. Push permission pending Maintainer or Owner action.
- **Deployment freedom**: Architecture is config-driven so we can run on user's laptop, on personal `m7g.medium` × 5 regions (current production target), or on course-provided `M7i.large` with one config change.

## Key Decisions

| Decision | Rationale | Outcome |
|---|---|---|
| Two-tier architecture (cloud collectors plus lab pipeline) | Per professor; matches prop firm practice; collectors stay lean, complexity moves to lab tier | — Pending |
| Multi-region collector deployment (5 distinct regions, one per venue, per ADR-0009 superseding ADR-0003) | Per professor; collectors near matching engines; avoids polluting per-venue latency measurements with off-axis traversal | ✓ Adopted 2026-05-08 |
| Three abstractions: TimestampSource, RecordSink, RecordSource | Decouples local dev from cloud production; migration is a config flip not a rewrite | — Pending |
| Use `data-stream.binance.vision` as Binance endpoint | Primary `stream.binance.com` returns HTTP 451 from US IPs; mirror serves identical data from same Tokyo region | ✓ Empirically validated 2026-04-20 |
| Binance dual-stream `@depth@100ms` + `@trade` (per ADR-0010 superseding ADR-0006) | Empirical 2026-05-08 finding: unbatched `@depth` flushes at ~1 Hz at the WS layer; dual stream gives 10x finer cadence plus per-event matching-engine `T` for latency decomposition | ✓ Adopted 2026-05-08 |
| Python asyncio prototype before C++ HW timestamps | Working pipeline first; C++ swap-in when timestamp precision actually matters; minimizes wasted work if scope shifts | — Pending |
| No Redis, no database, files only | Per professor; mirrors prop firm practice; minimizes overhead between feed and disk | — Pending |
| Project-scoped venv on Python 3.13.2 (pyenv) | Aligns with user's chosen global default; matches Amazon Linux 2023 install path | — Pending |
| Personal `m7g.medium` as named production target × 5 regions | Cheap (~$30/month each, ~$150/month total), PTP-supported, decouples progress from course provisioning timeline; M7i.large alternate if course infra arrives | — Pending |
| Per-venue collector packaging with `EXCHANGES` registry (`collector/exchanges/{venue}.py`) | Each EC2 instance runs one venue selected at deploy time by config; entrypoint resolves venue name to class via registry, no per-venue branching in callers | ✓ Adopted 2026-05-08 |
| Drop PTP-vs-NTP comparison from v1 (per ADR-0011) | Comparison is not on critical path; would require parallel NTP-only infra; honest scope > aspirational deliverable | ✓ Adopted 2026-05-08 |

---
*Last updated: 2026-05-08 after Kraken→OKX swap (ADR-0009), Binance dual-stream pivot (ADR-0010), and PTP-vs-NTP descope (ADR-0011)*
