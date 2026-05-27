# State: aws-ptp-crypto-recording

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-05-08)

**Core value:** Characterize feed latency and consolidated-book staleness with PTP-grade precision across five venues from five distinct AWS regions.

**Current focus:** Phase 1 (Local end-to-end with Binance, laptop only). Binance collector v1 is implemented with the dual-stream subscription per ADR-0010; remaining work is wiring the entrypoint and `LocalParquetSink.flush()`.

## Phase Status

| Phase | Status | Plans complete | Notes |
|---|---|---|---|
| 1: Local end-to-end with Binance | ◆ In Progress | 1/2 (advanced) | Scaffold complete (quick task 1). Per-venue collector packaging plus Binance v1 implementation shipped 2026-05-08. Remaining: `LocalParquetSink.flush()` PyArrow batched-write, `python -m collector` entrypoint, end-to-end Parquet recording test. |
| 2: Remaining venues + lab-tier pipeline | ○ Pending | 0/3 | Still laptop-only. Closes the two-tier loop with Coinbase as the second venue, then OKX, Kalshi, Polymarket. |
| 3: Cloud deployment + S3 + PTP | ○ Pending | 0/3 | Production target is personal `m7g.medium` × 5 regions (~$150/month total). Course-provided `M7i.large` is the alternate path if provisioned. |
| 4: PTP HW timestamps + C++ + final analytics | ○ Pending | 0/3 | Requires PTP infra (Phase 3). C++ collector replaces only the timestamp-acquisition layer per ADR-0005. |

## Last Activity

Updated: 2026-05-08

Today's deliverables:

- Per-venue collector packaging shipped: `collector/exchanges/{binance,coinbase,okx,kalshi,polymarket}.py` plus `EXCHANGES` registry in `collector/exchanges/__init__.py`. Binance is the v1 reference implementation; the other four are NotImplementedError skeletons.
- Binance collector v1 implements combined-stream subscription `@depth@100ms` + `@trade` per ADR-0010 (supersedes ADR-0006 after empirical 2026-05-08 finding that unbatched `@depth` flushes at ~1 Hz at the WS layer with ~130 events bundled per frame).
- 5-region deployment plan adopted (ADR-0009 supersedes ADR-0003): Binance ap-northeast-1, Coinbase us-east-1, Kalshi us-east-2, Polymarket eu-west-2, OKX ap-east-1. Kraken removed from venue list, OKX added.
- PTP-vs-NTP comparison dropped from v1 deliverables (ADR-0011): `t_ntp` field removed from `Timestamps` dataclass; proposal sections 6, 8, 10 updated; ROADMAP and REQUIREMENTS adjusted (33 v1 reqs → 31).
- Production instance target reframed: `m7g.medium` (~$30/month each, smallest PTP-supported size in m7g family) is named primary across all 5 regions; M7i.large is alternate if course infra arrives.
- First weekly report shipped: `docs/weekly-reports/2026-W19.md` covers all work since project init (2026-04-20).
- All living docs (CLAUDE.md, README.md, UPDATE.md, CHANGELOG.md, proposal.md, PROJECT.md, REQUIREMENTS.md, ROADMAP.md, questions.md, decisions/README.md) refreshed to current scope.

Earlier (2026-04-29): Completed quick task 1: scaffold repo and abstractions. Concrete `ClockGettimeSource` working; smoke-tested.

Project initialized 2026-04-20.

Architecture pivot 2026-04-28: adopted UPDATE.md (two-tier cloud + lab, three abstractions for migration-friendly deployment, pragmatic Python-first build order). Re-phased ROADMAP.md from 4 phases (collector / infra / C++ / analytics) to 4 phases (local-EE / venues+lab / cloud-deploy / C++-and-final-analytics).

Pre-Phase-1 exploration: `analysis/binance_data_stream_explore.ipynb` validated Binance data-stream connectivity and the `E - local_receive` latency-measurement methodology.

## Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|---|---|---|---|
| 1 | scaffold repo and abstractions | 2026-04-29 | _pending user commit_ | [1-scaffold-repo-and-abstractions](./quick/1-scaffold-repo-and-abstractions/) |

## Open Questions Affecting Roadmap

See `docs/questions.md` for the full running list. Items still blocking professor input:

- Team leader election (course rule; required before next Canvas submission cycle)
- AI/ML component scope (could add Phase 5)
- Real-time vs batch consolidated book (could split Phase 2 or 3)
- Prediction market instruments (concretizes COLLECT-04 and COLLECT-05)
- Team task split across four members
- VM provisioning timeline OR authorization to proceed on personal `m7g.medium` × 5

New as of 2026-05-08 (from ADR-0009 and ADR-0010 risk analyses):

- Kalshi matching engine metro: confirms `us-east-2` (Ohio) vs alternative `us-east-1` (NYC) placement
- OKX `ap-east-1` reachability: empirical verification before infra commit
- Polymarket `eu-west-2` vantage point framing: acceptable, or does "near matching engine" require a US region?
- Multi-region `data-stream.binance.vision` reachability: each AWS deployment region needs verification before launching collectors there
- Single-day Binance `@depth` 1 Hz observation: persistent across symbols/time, or single-day artifact? (team-side empirical follow-up)

---
*Last updated: 2026-05-08*
