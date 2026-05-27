# CLAUDE.md

## Project

**aws-ptp-crypto-recording**: PTP-synchronized cross-exchange market data recording pipeline.

Semester-long IE421 group project, supervised by Professor David Lariviere. Team of four. Primary deliverable is the GitLab repo.

Two-tier architecture per professor: cloud-tier collectors record exchange WS feeds with PTP/NIC timestamps and write to S3; lab-tier VM continuously pulls from S3, validates integrity, builds order books, runs analysis.

Living architecture decisions in `UPDATE.md`. Original specification in `docs/proposal.md`. Open questions for the professor in `docs/questions.md`.

## Course Rules

Non-negotiable per course policy:

- **Git discipline**: Commit and push to GitLab every day you work. No commits = assumed not working.
- **Individual attribution**: All work attributable via git history. Break work into separately committable chunks. No pair programming on the same code block.
- **Communication**: Discord (group channel) or recorded weekly Zoom only. No DMs, email, WeChat, text. English only.
- **Team leader**: Elected by unanimous consent. Submits weekly reports to Canvas + Box.
- **Quality bar**: Mediocre output will not receive a good grade regardless of meeting proposal scope.

## Repo Conventions

```
collector/                   # Python collectors (cloud tier)
  base_collector.py          # Collector ABC
  config_loader.py           # RECORDING_CONFIG-driven YAML loader
  timestamp/                 # swappable TimestampSource implementations
  exchanges/                 # per-venue collectors + EXCHANGES registry (binance is the v1 reference impl; coinbase/okx/kalshi/polymarket are skeletons)
sinks/                       # RecordSink (base + LocalParquetSink + S3ParquetSink stub)
pipeline/                    # Lab tier
  sources/                   # RecordSource (base + LocalParquetSource + S3ParquetSource stub)
                             # planned: validator.py (seq_num gap detection), book_builder.py (per-venue L2), consolidated_book.py (cross-venue merge)
analysis/                    # notebooks + analytics (binance_data_stream_explore.ipynb)
config/                      # exchanges.yaml, recording.local.yaml, recording.aws.yaml
docs/
  proposal.md                # original specification
  questions.md               # open questions for the professor
  decisions/                 # ADRs (immutable; supersede via new ADRs, never edit)
  weekly-reports/            # team-leader weekly digest, mirrored from Canvas + Box
tests/
  smoke_binance.py           # connectivity check against live .vision feed
data/                        # gitignored
                             # planned: infra/ for AWS, PTP, S3 setup scripts
```

## Multi-Region Layout

Per professor: collectors live near each exchange's matching engine. Five venues span five distinct AWS regions, one collector per region.

| Venue          | AWS Region                                                                 |
| -------------- | -------------------------------------------------------------------------- |
| Binance Global | `ap-northeast-1` (Tokyo)                                                   |
| Coinbase Spot  | `us-east-1` (N. Virginia)                                                  |
| Kalshi         | `us-east-2` (Ohio, closest to Chicago metro)                               |
| Polymarket     | `eu-west-2` (London)                                                       |
| OKX            | `ap-east-1` (Hong Kong, closest to OKX's Alibaba Cloud HK matching engine) |

Cross-region timestamps are valid because all AWS regions reference the same atomic clock fleet. OKX runs on Alibaba Cloud HK rather than AWS-native infra, so ap-east-1 is an intentional "near but not co-located" vantage point for the analysis.

## Tech Stack

- **Cloud tier**: Python asyncio for prototype and steady-state. C/C++ (Boost.Asio/Beast) replaces only the timestamp-acquisition layer when SO_TIMESTAMPING is required.
- **Lab tier**: Python (PyArrow, Pandas, DuckDB).
- **Transport (optional, later)**: ZMQ pub/sub for live fan-out.
- **Infra**: AWS EC2 `m7g.medium` (ARM Graviton, smallest PTP-supported size, ~$30/month per region), Amazon Linux 2023, ENA driver 2.16.1g with `phc_enable=1`, chrony with PHC0. Verified working in production (Tokyo, 2026-05-15); the earlier "ARM64 doesn't support PTP" reading was a transient driver/AMI/kernel-param misdiagnosis. M7i.large (Intel) is a supported alternate.
- **Storage**: Parquet files local then synced to S3.
- **Time**: PTP via chrony plus ENA hardware clock; SO_TIMESTAMPING for NIC packet timestamps in the C++ build.

## Migration-Friendly Architecture

Three abstractions decouple local development from cloud production. All config-driven via `RECORDING_CONFIG` env var (`local` or `aws`):

1. **TimestampSource**: `ClockGettimeSource` (laptop), `PTPClockGettimeSource` (EC2 with chrony plus PHC0), `NICHwTimestampSource` (C++ with SO_TIMESTAMPING).
2. **RecordSink**: `LocalParquetSink`, `S3ParquetSink`.
3. **RecordSource**: `LocalParquetSource`, `S3ParquetSource`.

Migrating from "Yichen's laptop" to production EC2 is a config flip, not a rewrite. Production target is `m7g.medium` (ARM Graviton), one per region across the 5-region layout (Tokyo deployed and recording as of 2026-05-15). M7i.large remains a viable alternate; PTP plumbing is identical on both.

## Pragmatic Build Order

Per UPDATE.md:

1. Repo scaffold and abstract interfaces (no concrete logic yet).
2. Binance collector with Python asyncio plus `ClockGettimeSource` plus stdout, on laptop.
3. `LocalParquetSink` writing to `./data/`.
4. Coinbase collector (second venue, validates the pattern).
5. Lab-tier prototype: `LocalParquetSource` plus validator plus book_builder.
6. Consolidated cross-venue book.
7. Latency analysis notebook (preliminary, using `clock_gettime` data).
8. Remaining venues (OKX, Kalshi, Polymarket).
9. C++ collector with SO_TIMESTAMPING (after professor confirms timing requirements; on `m7g.medium`, or whatever instance is current).
10. S3 sink and source (boto3; drops in via config flip).

Steps 1-8 are fully portable: laptop today, `m7g.medium` per region in the 5-region layout (Tokyo deployed 2026-05-15), M7i.large as a viable alternate. Same code, different config.

## What We Measure (and What We Don't)

**Are**: relative latency across venues from a fixed vantage point per region. Distribution of `t_nic_first - t_exchange` per venue over time. Multi-packet WS message reassembly profiles.

**Are not**: absolute exchange-internal processing latency. We cannot decompose `t_nic_first - t_exchange` into network versus exchange-internal components. State the vantage point and report what is genuinely measurable.

## Key Context

- PTP runs at the OS level via chrony. App code reads `clock_gettime(CLOCK_REALTIME)` and gets a PTP-disciplined clock for free, no special PTP library needed.
- **PTP infrastructure: operational on Tokyo (ap-northeast-1) as of 2026-05-15.** chrony tracks PHC0 with sub-microsecond RMS offset; the BinanceCollector + `PTPClockGettimeSource` path produces delta_ns medians of 1.4-4.4 ms across @depth@100ms and @trade streams, well within the 5-30 ms target.
- **Python CAN access `SO_TIMESTAMPING`** via raw sockets + sans-IO WS framing (wsproto + `ssl.MemoryBIO`). The high-level `websockets` library buffers ahead of the kernel socket and blocks the ancillary-data path (Q7 spike, 2026-05-15). P2 implements a Python NIC HW timestamp source via the wsproto + MemoryBIO path; C++ Boost.Beast remains the fallback. See ADR-0012.
- **P2 NIC HW timestamps deployed and verified on Tokyo as of 2026-05-16. SIOCSHWTSTAMP ioctl required for AWS Nitro/ENA; automated via systemd ExecStartPre.** NIC hardware timestamps on 100% of `binance_nic` records; userspace jitter (t_ptp - t_nic_first) p50 153 us (depth) to 1.0 ms (trade). The Python NIC-HW path is empirically proven; ADR-0005 ("C++ needed for HW") is superseded by ADR-0012. Production `binance` (PTPClockGettimeSource) keeps running untouched as the comparison baseline.
- **`coinbase_nic` and `okx_nic` exist and are deploy-ready (built 2026-05-16), pending regional EC2 instances.** Same subclass-and-override-`run()` pattern as `binance_nic` (override `run()` only, inherit `parse()`, `venue` stays the parent value, sink path split by `--venue`). Registered in `EXCHANGES`; valid `--venue` args. They subscribe post-handshake via the new `RawWebSocketClient.send()` (Coinbase: one `subscribe` per channel; OKX: one combined `op:subscribe`). Deploy command and procedure in `infra/README.md` "Deploying additional regions" (Coinbase→us-east-1, OKX→ap-east-1). Their NIC hardware stamps depend on the SIOCSHWTSTAMP `ExecStartPre`, which as of 2026-05-17 is committed (`infra/scripts/enable-hw-timestamping.sh` + the `ExecStartPre=+...` line in the systemd unit) and matches the unit running on Tokyo; a fresh region picks both up via git clone + `install.sh` with no manual step. Production `coinbase`/`okx` base classes are untouched and remain the clock_gettime baseline path.
- This project is about measurement and analysis, not trading. Characterizing feed latency, not optimizing execution speed.
- Binance access from US IPs requires `wss://data-stream.binance.vision`. The `.com` host returns HTTP 451 (regulatory geo-block). Empirically validated 2026-04-20. See ADR-0001.
- Binance subscribes to a combined `@depth@100ms` plus `@trade` stream. Empirical 2026-05-08 finding: unbatched `@depth` flushes at ~1 Hz at the WS layer with ~130 matching-engine events bundled per frame, so it does not preserve sub-second cadence. The dual-stream subscription is the measurement contract; do not "simplify" back to single-stream and do not make the stream choice YAML-tunable. See ADR-0010.
- Per-venue collectors live in `collector/exchanges/{venue}.py` and register in the `EXCHANGES` dict in `collector/exchanges/__init__.py`. To add a venue, write the class subclassing `Collector`, add to the registry, add the YAML entry in `config/exchanges.yaml`. Each EC2 instance runs one venue, selected at deploy time by config.
- ADRs in `docs/decisions/` are immutable. To revise a decision, write a new ADR with status `Accepted, supersedes ADR-NNNN` and flip the old ADR's status to `Superseded by ADR-MMMM`. Never edit ADR content after acceptance.
- No Redis. No database. Files only. Per professor.
