# UPDATE.md — Current State & Next Steps

_Last updated: May 16, 2026_

This document captures the latest decisions from professor feedback and our research, and defines the architecture so we can build now (on a local/personal machine) and migrate cleanly to the official EC2 instances when provisioned. **The core principle: do not let infra provisioning be a bottleneck.**

---

## 0. Current Status (May 15, 2026)

### Tokyo deployment complete

P1 (deploy preparation + verify) is done. The AWS ap-northeast-1 Tokyo EC2 instance runs the `BinanceCollector` via systemd under `RECORDING_CONFIG=aws`, subscribed to `btcusdt@depth@100ms` + `btcusdt@trade` + `ethusdt@depth@100ms` + `ethusdt@trade` on `data-stream.binance.vision`. Parquet output lands in `./data/binance/<date>/` and `aws s3 sync` pushes to `s3://group19-ptp-tokyo/` every 5 minutes via cron.

Verify-capture delta_ns medians: **1.4-4.4 ms across both streams**, well inside the <50 ms median / <200 ms p99 gate. `chronyc tracking` shows `Reference ID: PHC0` with sub-microsecond RMS offset. PTP infrastructure is solid.

### Q7 spike result (2026-05-15)

Tested whether the Python `websockets` library exposes the underlying socket enough for external `recvmsg` to extract `SCM_TIMESTAMPING` ancillary data:

- Socket exposed ✓
- `setsockopt SO_TIMESTAMPING` succeeded ✓
- WS frames continued to flow ✓
- `recvmsg` returned `BlockingIOError`: **the library is buffering ahead of the kernel socket**

Conclusion: path (a) "hijack the websockets library's socket" does not work. P2 requires path (b): manual WS framing over a raw socket with `recvmsg` + `cmsghdr` parsing.

### Mark done

- ✅ Repo scaffold + abstract interfaces (step 1 of build order)
- ✅ Binance collector via Python asyncio + `ClockGettimeSource` (step 2)
- ✅ `LocalParquetSink` writing to `./data/` (step 3)
- ✅ Tokyo EC2 deploy with `PTPClockGettimeSource` via systemd
- ✅ S3 sync cron pushing to `s3://group19-ptp-tokyo/`
- ⏳ Coinbase / OKX / Kalshi / Polymarket collectors (skeletons + partial implementations landed 2026-05-15; deploy after P2 lands)
- ⏳ Lab-tier prototype (`tools/lab_validator.py` + `tools/cross_venue_latency.py` landed 2026-05-15 as a head-start)
- ✅ P2 NIC HW timestamp source — deployed and verified on Tokyo 2026-05-16 (option (ii) wsproto + `ssl.MemoryBIO`)

### P2 complete — NIC HW timestamps verified on Tokyo (2026-05-16)

**Owner:** Yichen.

Option (ii) per ADR-0012, shipped. The path:

- `collector/transport/raw_ws.py` — `RawWebSocketClient`: raw TCP socket with `SOF_TIMESTAMPING_RX_HARDWARE | RX_SOFTWARE | RAW_HARDWARE`, hand-driven `ssl.MemoryBIO` TLS, `wsproto` WS framing, `recvmsg` + `SCM_TIMESTAMPING` cmsg parse per chunk.
- `collector/timestamp/nic_hw_source.py` — `NICTimestampSource` (per-message, constructed with the chunk timestamps; the registry stub `NICHwTimestampSource` is kept for entrypoint-import safety).
- `collector/exchanges/binance_nic.py` — subclasses `BinanceCollector`, overrides `run()` only; `parse()` inherited unchanged. Selected via `--venue binance_nic` from the `EXCHANGES` registry.
- `sinks/local_parquet_sink.py` — `t_nic_first`/`t_nic_last` written as `_ns`-suffixed columns; `packet_metadata` as `list<struct<t_ns,byte_count>>`. Production `binance` schema unchanged (no strict schema; cross-dataset queries use DuckDB `union_by_name=true`).

**Tokyo verification (2026-05-16):** NIC hardware timestamps populate **100% of `binance_nic` records**. Userspace jitter (`t_ptp_ns - t_nic_first_ns`): p50 153 us (depth streams) to 1.0 ms (trade streams); p99 1.4 ms (depth) to 30 ms (trade, asyncio scheduling under burst). `avg_chunks` per message 1.01-1.20 after the attribution fix (chunks accumulated since the last `recvmsg` attribute to every WS message decoded before the next, per proposal section 6).

**Deployment finding:** AWS Nitro / ENA ships RX hardware timestamping disabled. The `SIOCSHWTSTAMP` ioctl (`HWTSTAMP_FILTER_ALL`) must flip device-level RX config from `0` to `1`; `SO_TIMESTAMPING` alone is insufficient. Automated via `infra/scripts/enable-hw-timestamping.sh` as a systemd `ExecStartPre` (root, idempotent, safe on both services). Not documented by AWS for the Python path. See ADR-0012 "Deployment addendum".

The production `binance` collector (`PTPClockGettimeSource`) continues running untouched as the comparison baseline. `binance_nic` runs alongside it on Tokyo. ADR-0005 (Python-prototype-then-C++) is now superseded by ADR-0012: the Python NIC-HW path is empirically proven, no C++ collector needed.

**Next:** production vs binance_nic comparison analysis (PTP-userspace vs NIC-hardware jitter) — the ADR-0012 writeup payload.

### Coinbase + OKX NIC collectors built and deploy-ready (2026-05-16)

`coinbase_nic` and `okx_nic` NIC-timestamped collectors built and ready for deployment to `us-east-1` and `ap-east-1` respectively. Deploy command documented in `infra/README.md` ("Deploying additional regions"). Same subclass-and-override-`run()` pattern as `binance_nic`: `collector/exchanges/coinbase_nic.py` subclasses `CoinbaseCollector`, `collector/exchanges/okx_nic.py` subclasses `OKXCollector`, both override `run()` only and inherit `parse()` unchanged. `RawWebSocketClient` gained a public `send()` coroutine for the post-handshake subscription frames (Coinbase sends one `subscribe` per channel; OKX one combined `op:subscribe`); Binance never needed it because its subscription is URL-encoded. Production `binance`/`binance_nic` and the `coinbase`/`okx` base classes are untouched. Verified: `py_compile`, registry import, `issubclass`, `parse` identity to parent, lazy `wsproto` import (production import path stays safe without wsproto installed).

**Drift corrected (2026-05-17):** the SIOCSHWTSTAMP `ExecStartPre` and `infra/scripts/enable-hw-timestamping.sh` were previously documented as deployed but lived only on the Tokyo box, not in the tree (flagged 2026-05-16). Both are now committed and match the unit running on Tokyo (`/etc/systemd/system/group19-collector@.service`): `enable-hw-timestamping.sh` applies the `SIOCSHWTSTAMP` ioctl (`HWTSTAMP_FILTER_ALL`) idempotently via the project venv, and the unit carries `ExecStartPre=+/home/ec2-user/aws-ptp-crypto-recording/infra/scripts/enable-hw-timestamping.sh` (the `+` runs it as root for CAP_NET_ADMIN). `install.sh` asserts the script exists and re-applies `+x`, so a fresh region picks up the unit and the script via git clone with no manual step. The repo is now the source of truth; box→repo drift is resolved. **Region-portable (2026-05-18):** the script no longer hardcodes `ens5`. Invoked with no argument (as the unit's `ExecStartPre` does), it auto-detects the active ENA interface (first non-loopback UP link, reliable because the unit orders After=network-online.target); an explicit interface arg overrides; `ens5` is used only as a last-resort fallback if detection finds nothing. Verified across all three branches. The Virginia/Hong Kong boxes therefore need no per-box interface check before deploying `coinbase_nic`/`okx_nic`. See ADR-0012 "Deployment addendum".

---

## 1. What's Settled

### Project shape (per Professor Lariviere)

> "The goal is to build a production-grade market data recording and processing pipeline — both recording in the cloud and a VM in the lab that continually accesses, copies, processes, and validates that data, just like what would be found at any prop firm."

Two-tier system:

- **Cloud tier** — lean recorders. Connect to exchange websockets, attach PTP/NIC timestamps, write to local files, sync to S3. Nothing else.
- **Lab tier** — a VM (Apache Guacamole, professor-provisioned) that continuously pulls from S3, validates integrity, builds order books, runs analysis.

### Multi-region collector layout

Per professor: collectors should be located near each exchange's data origin. Five venues span five distinct AWS regions:

| Venue | AWS Region | PTP-supported? | Rationale |
|---|---|---|---|
| Binance Global | `ap-northeast-1` (Tokyo) | Yes | Matching engine in Tokyo, per Group 11 (Spring 2024) |
| Coinbase Spot | `us-east-1` (N. Virginia) | Yes | AWS-native |
| OKX | `ap-east-1` (Hong Kong) | Yes | OKX runs on Alibaba Cloud HK (non-AWS-native); ap-east-1 is "near but not co-located", the most interesting non-AWS data point |
| Kalshi | `us-east-2` (Ohio) | Yes | Closest AWS region to Chicago metro |
| Polymarket | `eu-west-2` (London) | Yes | London vantage point |

Cross-region timestamp comparison is valid because all AWS regions reference the same atomic clock fleet.

### Instance type

**`m7g.medium`** — the smallest PTP-supported size in the m7g (Graviton ARM) family. Roughly ~$30/month each, ~$150/month total for the 5-region deployment. M7i.large (Intel) is also PTP-supported and remains the alternate target if course infra is provisioned, but `m7g.medium` is the current production choice. Other PTP-supported families: M7a/g, R7a/g/i, I8g/ge.

### Timestamping: SO_TIMESTAMPING (NIC HW level) required

Professor explicitly: "the hardware timestamp of the NIC and all other data from the exchange." This means:

- The **collector hot path** must use `SO_TIMESTAMPING` to read kernel-attached hardware timestamps from the NIC. Python cannot do this — collector core needs C/C++ (Boost.Asio/Beast pattern, like Group 04's `TimestampAwareStream`).
- Everything downstream of the collector — parsing, normalization, book building, analysis — stays Python.

**Pragmatic build order**: write a Python asyncio prototype using `clock_gettime(CLOCK_REALTIME)` as a **placeholder timestamp source**. This lets us build and test the entire pipeline locally, immediately. The C++ collector replaces only the timestamp-acquisition layer later. Schema is identical either way.

### Data schema (per message)

| Field | Type | Source |
|---|---|---|
| `venue` | string | collector config |
| `symbol` | string | parsed |
| `msg_type` | enum (snapshot/delta) | parsed |
| `seq_num` | uint64 | exchange payload |
| `t_exchange` | uint64 ns | exchange payload |
| `t_nic_first` | uint64 ns | HW NIC timestamp of first TCP packet (placeholder: `clock_gettime` until C++ collector exists) |
| `t_nic_last` | uint64 ns | HW NIC timestamp of last packet |
| `t_userspace` | uint64 ns | `clock_gettime` after parse |
| `packet_metadata` | array[(hw_ts, byte_count)] | per-packet info |
| `bids`, `asks` | array[(price, size)] | L2 levels |

### Storage / transport

- Parquet files written locally on collector → synced to S3 → pulled by lab VM.
- **No Redis, no database.** Professor explicit. Files only.
- Optional ZMQ pub/sub ticker plant for live fan-out. Build later.

### What we are and are not measuring

- **Are**: relative latency across venues from a fixed vantage point, distribution of `t_nic_first - t_exchange` per venue over time, multi-packet WS message reassembly profiles.
- **Are not**: absolute exchange-side processing latency (cannot decompose `t_nic_first - t_exchange` into network vs internal). State the vantage point and report what's actually measurable.

---

## 2. What We're Waiting On

| Item | Blocker? | Workaround |
|---|---|---|
| Course-provisioned EC2 instances | No | Personal `m7g.medium` × 5 regions is the named production target; course infra is the alternate if provisioned |
| PTP HW clock (`/dev/ptp_ena`) | No | Use `clock_gettime(CLOCK_REALTIME)` placeholder; same API surface |
| Apache Guacamole lab VM | No | Run lab-side pipeline on local machine for now |
| Final Polymarket API auth answer | No | Public CLOB endpoints are documented; start there |
| Binance public WS access from US IP | No | Use `data-stream.binance.vision` (not `stream.binance.com`); test empirically |

**Nothing in the queue is a hard blocker.** Everything we build right now ports to the official infra without code changes if we follow the abstraction rules below.

---

## 3. Migration-Friendly Architecture

The goal is that switching from "Yichen's laptop" to "personal `m7g.medium` per region" (or to "course-provisioned M7i.large" if/when that arrives) is a config change, not a code change.

### Abstraction boundaries

Three things differ between local and official infra. Each gets a config-driven abstraction:

**1. Timestamp source.** A single interface that returns `(t_nic_first, t_nic_last, packet_metadata)` for a websocket message.

```
TimestampSource (abstract)
├── ClockGettimeSource   # local dev — clock_gettime around recv()
├── PTPClockGettimeSource # PTP-synced EC2 — same syscall, but clock is PHC0-disciplined
└── NICHwTimestampSource  # C++ collector with SO_TIMESTAMPING
```

Selected by env var / config: `TIMESTAMP_SOURCE=clock_gettime|ptp|nic_hw`. Downstream code never knows the difference.

**2. Storage backend.** Writes go through a `RecordSink` interface.

```
RecordSink (abstract)
├── LocalParquetSink   # writes to ./data/venue/YYYY-MM-DD/HH.parquet
└── S3ParquetSink      # writes locally then syncs to s3://bucket/venue/...
```

Config: `SINK=local|s3` and `S3_BUCKET=...`. Same Parquet schema either way.

**3. Lab-side data source.** Pipeline reads through a `RecordSource` interface.

```
RecordSource (abstract)
├── LocalParquetSource  # reads from ./data/
└── S3ParquetSource     # reads from s3://bucket/
```

### Repo layout

```
aws-ptp-crypto-recording/
├── CLAUDE.md
├── UPDATE.md                              # this file
├── README.md
├── CHANGELOG.md
├── requirements.txt
├── docs/
│   ├── proposal.md                        # original specification
│   ├── questions.md                       # open questions for the professor
│   ├── decisions/                         # ADRs (immutable; supersede via new ADRs)
│   └── weekly-reports/                    # team-leader weekly digest, mirrored from Canvas + Box
├── collector/                             # cloud tier
│   ├── base_collector.py                  # Collector ABC
│   ├── config_loader.py                   # RECORDING_CONFIG-driven YAML loader
│   ├── timestamp/
│   │   ├── base.py                        # TimestampSource ABC + Timestamps dataclass
│   │   ├── clock_gettime_source.py
│   │   ├── ptp_source.py                  # marker subclass; PTP-disciplined regime
│   │   └── nic_hw_source.py               # stub; real impl in C++ collector (Phase 4)
│   └── exchanges/                         # per-venue collectors + EXCHANGES registry
│       ├── __init__.py                    # registry: name → class
│       ├── binance.py                     # v1 reference impl (dual-stream per ADR-0010)
│       ├── coinbase.py                    # skeleton, NotImplementedError
│       ├── okx.py                         # skeleton, NotImplementedError
│       ├── kalshi.py                      # skeleton, NotImplementedError
│       └── polymarket.py                  # skeleton, NotImplementedError
├── sinks/
│   ├── base_sink.py
│   ├── local_parquet_sink.py
│   └── s3_parquet_sink.py
├── pipeline/                              # lab tier
│   ├── sources/
│   │   ├── base_source.py
│   │   ├── local_source.py
│   │   └── s3_source.py
│   └── # planned: validator.py, book_builder.py, consolidated_book.py
├── analysis/
│   └── binance_data_stream_explore.ipynb  # latency-measurement methodology validation
├── config/
│   ├── exchanges.yaml                     # per-venue WS endpoints + symbols
│   ├── recording.local.yaml               # for laptop (RECORDING_CONFIG=local)
│   └── recording.aws.yaml                 # for EC2 (RECORDING_CONFIG=aws)
├── tests/
│   └── smoke_binance.py                   # connectivity check against live .vision feed
└── data/                                  # gitignored, Parquet shards land here
# planned: infra/ for AWS, PTP, S3 setup scripts
```

### Config-driven environment

Every place where local vs production differs is in `config/recording.*.yaml`. Code reads `RECORDING_CONFIG=local|aws` env var and loads the right file. No hardcoded paths, no hardcoded clock sources, no hardcoded buckets.

---

## 4. What We Can Build This Week (No Official Infra Required)

Ordered for fastest end-to-end first:

1. **Repo scaffold** — directory structure above, `CLAUDE.md`, `UPDATE.md`, `README.md`, gitignore, base abstract classes (empty implementations OK).
2. **Binance collector (Python asyncio)** — connect to `data-stream.binance.vision` combined stream (`@depth@100ms` + `@trade`, see ADR-0010), parse, attach `clock_gettime` timestamp via `ClockGettimeSource`, log to stdout. ~50 lines.
3. **`LocalParquetSink`** — batch records (e.g. 1000 messages or 5 seconds), write to `./data/binance/YYYY-MM-DD/HH.parquet` via PyArrow.
4. **Coinbase collector** — second venue, prove the collector pattern generalizes. Same sink.
5. **Local pipeline prototype** — `LocalParquetSource` → `validator` (gap detection on `seq_num`) → `book_builder` (per-venue L2 book reconstruction) → simple stdout.
6. **Consolidated book** — merge Binance + Coinbase ladders, compute cross-venue best bid/ask.
7. **Analysis notebook** — load a few hours of recorded data, plot `t_userspace - t_exchange` distribution per venue.
8. **Add Kalshi, Polymarket, OKX collectors** — same pattern.
9. **C++ collector + SO_TIMESTAMPING** (only after professor confirms timing requirements and once we have a PTP-supported instance to test on; `m7g.medium` qualifies). Implements `NICHwTimestampSource` interface.
10. **S3 sink + S3 source** — straightforward boto3 wrapping, drops in via config flip.

Steps 1–8 are fully portable. They run on Yichen's laptop today, on personal `m7g.medium` per region, on course-provisioned `M7i.large` if/when that shows up — same code, different config.

### Day-zero git discipline (per course rules)

- Push to GitLab every day work happens.
- One feature per branch, one commit per logical unit, attributable to one teammate.
- No DMs, no email, no WeChat for project discussion. Discord channel + recorded Zoom only.
- Issues in GitLab for every task.

---

## 5. Open Questions for Professor

These don't block building but should be raised at the next meeting:

1. **Confirm SO_TIMESTAMPING is required**, or is PTP-disciplined `clock_gettime` acceptable. (Big effort difference.)
2. **AWS budget / credits** — confirm coverage for five `m7g.medium` instances + S3 (current target), or alternatively M7i.large if course infra is provisioned instead.
3. **Provisioning timeline** for the official EC2 instances and the lab Guacamole VM.
4. **Polymarket data feed expectations** — are we using the public CLOB WS, or do they want gamma/on-chain too?
5. **Final scope on AI/ML component** — anomaly detection across venues vs natural-language query interface vs both.

---

## 6. Quick-Reference Decisions

- Regions (one per venue): `ap-northeast-1` Binance / `us-east-1` Coinbase / `us-east-2` Kalshi / `eu-west-2` Polymarket / `ap-east-1` OKX
- Instance: `m7g.medium` (current; M7i.large is alt), Amazon Linux 2023, ENA driver ≥ 2.10.0
- Clock: chrony with `refclock PHC /dev/ptp_ena prefer`
- Depth: L2 (snapshots + deltas)
- Storage: Parquet → S3
- Transport (optional, later): ZMQ pub/sub
- Collector hot path: C/C++ with `SO_TIMESTAMPING` (eventually)
- Everything else: Python (asyncio, PyArrow, Pandas, DuckDB)
- No Redis. No database. Files.
