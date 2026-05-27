# aws-ptp-crypto-recording

PTP-synchronized cross-exchange market data recording pipeline. It records
crypto and prediction-market order book and trade feeds with NIC-hardware and
PTP-disciplined timestamps, so cross-venue feed latency can be measured at a
precision NTP cannot reach.

IE421 High Frequency Trading, Spring 2026, Group 19. Supervised by Professor
David Lariviere. This is a measurement and analysis project, not a trading
system.

## Current status (2026-05-22)

- **Tokyo is live with NIC hardware timestamps.** AWS `ap-northeast-1` runs
  two Binance collectors via systemd: the baseline `binance` (PTP-disciplined
  userspace clock) and `binance_nic` (NIC hardware timestamps). Both record 8
  symbols (ADAUSDT, AVAXUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, LINKUSDT, SOLUSDT,
  XRPUSDT) across `@depth@100ms` + `@trade` (16 streams), syncing to
  `s3://group19-ptp-tokyo/` every 5 minutes.
- **PTP verified.** `chronyc tracking` shows `Reference ID: PHC0`, 118 ns RMS
  offset, 67 ns system offset.
- **P2 complete: NIC hardware timestamps.** The wsproto + `ssl.MemoryBIO` path
  produces nanosecond NIC hardware stamps on 100% of latency-valid
  `binance_nic` records ([ADR-0012](docs/decisions/0012-p2-path-selection.md)).
  AWS Nitro requires a device-level `SIOCSHWTSTAMP` ioctl beyond
  `SO_TIMESTAMPING`, or the stamps silently return zero; this is the project's
  featured empirical finding.
- **5-venue framework, NIC variants built.** `binance`/`binance_nic` deployed;
  `coinbase`/`coinbase_nic` and `okx`/`okx_nic` built and deploy-ready; Kalshi
  auth-scaffolded (needs keys); Polymarket public-feed implemented. All emit
  the same Parquet schema.
- **Final report delivered.** [docs/final_report.md](docs/final_report.md)
  ([PDF](docs/final_report.pdf)), with the analysis snapshot in
  [analysis/2026-05-21/](analysis/2026-05-21/) and a 45-second pitch outline in
  [docs/pitch_45s_outline.md](docs/pitch_45s_outline.md).

## Headline results (Tokyo, 17.51 h, Binance NIC hardware path)

- **9,257,886 records** over 17.51 hours, 16 streams, 14,243 Parquet files.
- **Wire-arrival latency** (NIC hardware stamp minus exchange event time): p50
  **1.382 ms**, p99 6.627 ms.
- **Userspace pickup lag** (userspace clock minus NIC stamp): p50 **211 µs**.
- **TCP coalescing:** 51.77% of records arrived coalesced, overwhelmingly
  trade-stream traffic (87.05% of trades versus 0.46% of depth).
- Stream type, not symbol, dominates latency variation. Full analysis and
  charts: [docs/final_report.md](docs/final_report.md).

Live phase tracker: [.planning/STATE.md](.planning/STATE.md). One-page status
for graders: [docs/status_snapshot_2026-05-16.md](docs/status_snapshot_2026-05-16.md);
full writeup: [docs/final_report.md](docs/final_report.md).

## Architecture in two sentences

Lean cloud collectors (one AWS region per venue, near each matching engine)
attach NIC-hardware and PTP-disciplined timestamps and write Parquet, synced to
per-region S3 buckets. A lab tier pulls from S3, validates sequence continuity,
builds per-venue order books, and runs latency analysis. Full detail:
[UPDATE.md](UPDATE.md) and [docs/proposal.md](docs/proposal.md).

The collector is built on three swappable, config-driven abstractions
(`TimestampSource`, `RecordSink`, `RecordSource`) so moving from laptop to EC2
is a config flip, not a rewrite. `TimestampSource` has three implementations:
`ClockGettimeSource` (laptop), `PTPClockGettimeSource` (EC2 baseline), and
`NICHwTimestampSource` (NIC hardware). See
[ADR-0004](docs/decisions/0004-three-abstractions-for-migration.md) and
[ADR-0012](docs/decisions/0012-p2-path-selection.md).

## Quick start (local)

```bash
git clone git@gitlab.engr.illinois.edu:ie421_high_frequency_trading_spring_2026/ie421_hft_spring_2026_group_19/group_19_project.git
cd group_19_project

python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Connectivity smoke test against the live Binance .vision feed
.venv/bin/python tests/smoke_binance.py

# Run the Binance collector locally (writes Parquet to ./data/binance/)
.venv/bin/python -m collector.entrypoint --venue binance
# ^C to stop; the sink flushes on exit

# Validate sequence continuity on what you just recorded
.venv/bin/python tools/lab_validator.py binance --data-dir data/

# Generate the baseline analysis report + charts
.venv/bin/python tools/produce_analysis_report.py --venue binance --data-dir data/
```

`RECORDING_CONFIG=local` (default) uses `ClockGettimeSource` +
`LocalParquetSink`. `RECORDING_CONFIG=aws` uses the PTP-disciplined path +
the config in [config/recording.aws.yaml](config/recording.aws.yaml). The
NIC-hardware path (`--venue binance_nic`) relies on Linux `SO_TIMESTAMPING`
plus the `SIOCSHWTSTAMP` ioctl and is intended for the EC2 deployment, not a
laptop.

Valid `--venue` values: `binance`, `binance_nic`, `coinbase`, `coinbase_nic`,
`okx`, `okx_nic`, `kalshi`, `polymarket`.

## Deploying to a new region

Full procedure in [infra/README.md](infra/README.md). Short version:

```bash
# One-time bucket creation (geographic naming: group19-ptp-<region>)
aws s3api create-bucket --bucket group19-ptp-<region> --region <aws-region> \
  --create-bucket-configuration LocationConstraint=<aws-region>

# On the EC2 box, after venv setup and PTP verification:
sudo ./infra/scripts/install.sh <region-short> <venue>
sudo systemctl start group19-collector@<venue>
```

Region-short names: `tokyo`, `virginia`, `ohio`, `london`, `hong-kong`. The
systemd unit ([infra/systemd/group19-collector@.service](infra/systemd/group19-collector@.service))
is a template; `@<venue>` selects the collector. The NIC-hardware collectors
depend on `SIOCSHWTSTAMP` being enabled, which `install.sh` wires as a systemd
`ExecStartPre` ([infra/scripts/enable-hw-timestamping.sh](infra/scripts/enable-hw-timestamping.sh)),
so a fresh region picks it up with no manual step.

## Where things live

| What | Where |
|---|---|
| Final report | [docs/final_report.md](docs/final_report.md) ([PDF](docs/final_report.pdf)) |
| 45-second pitch outline | [docs/pitch_45s_outline.md](docs/pitch_45s_outline.md) |
| Analysis snapshot + charts | [analysis/2026-05-21/](analysis/2026-05-21/) |
| Current architecture of record | [UPDATE.md](UPDATE.md) |
| Original proposal | [docs/proposal.md](docs/proposal.md) |
| Architecture decisions (ADRs) | [docs/decisions/](docs/decisions/) |
| One-page status for graders | [docs/status_snapshot_2026-05-16.md](docs/status_snapshot_2026-05-16.md) |
| Open questions for professor | [docs/questions.md](docs/questions.md) |
| Project chronology | [CHANGELOG.md](CHANGELOG.md) |
| Cloud collectors | [collector/](collector/) |
| Storage abstractions | [sinks/](sinks/) and [pipeline/sources/](pipeline/sources/) |
| Lab-tier tools | [tools/](tools/) |
| Deploy assets | [infra/](infra/) |
| Claude operating manual | [CLAUDE.md](CLAUDE.md) |

## Where the data lives

Per-region S3 buckets, geographic naming `group19-ptp-<region>`:

| Region | Bucket |
|---|---|
| Tokyo (`ap-northeast-1`) | `group19-ptp-tokyo` (live) |
| N. Virginia (`us-east-1`) | `group19-ptp-virginia` |
| Ohio (`us-east-2`) | `group19-ptp-ohio` |
| London (`eu-west-2`) | `group19-ptp-london` |
| Hong Kong (`ap-east-1`) | `group19-ptp-hong-kong` |

Layout inside a bucket: `<venue>/<YYYY-MM-DD>/<flush_ns>.parquet`. The baseline
and NIC-hardware paths write separate prefixes (`binance/` and `binance_nic/`).
Files are immutable once flushed; the lab tier reads them via DuckDB.

## Open work + recommended next steps

1. **Deploy a second region** to unlock cross-venue analysis. `coinbase_nic`
   (Virginia) and `okx_nic` (Hong Kong) are built and deploy-ready; only the
   EC2 instance and bucket are needed. Procedure in
   [infra/README.md](infra/README.md). This is the natural next task now that
   the NIC-hardware path is verified.
2. **Kalshi auth:** fill `api_key_id` + `private_key_path` in
   [config/exchanges.yaml](config/exchanges.yaml), `pip install cryptography`.
3. **Coinbase L2:** currently `market_trades` + `ticker` only; full `level2`
   needs API-key auth.
4. **Cross-venue matching window:** stubbed in
   [tools/cross_venue_latency.py](tools/cross_venue_latency.py); needs real
   multi-region data to tune.
5. **Schema cleanup:** `payload_json` preserves every raw message and dominates
   on-disk size; a follow-up could drop or compress it once replay needs settle.
6. **C++ Boost.Beast collector:** a mapped fallback for the NIC path
   ([ADR-0012](docs/decisions/0012-p2-path-selection.md)); optional, since the
   Python path is verified in production.

## Course rules (non-negotiable)

Daily commits to GitLab when working; individual attribution per commit (no
pair programming on the same code block); communication on Discord group
channel and recorded weekly Zoom only (no DMs/email/WeChat, English only);
weekly reports submitted by team leader to Canvas + Box.

## Team & contact

Individual attribution is captured by the GitLab commit history.

- **yichen32** (Yichen Yan): infrastructure, architecture, software pipeline,
  Tokyo deployment, schema design, the NIC-hardware path, and the
  `SIOCSHWTSTAMP` finding.
- **aryac5** (Arya Chhabra): cost analysis and instance sizing, plus collector
  and lab-tier engineering (Binance REST depth-snapshot bootstrap, Coinbase
  level-2 parser, the L2 `book_builder`, `book_replay`, and the sequence-gap
  `validator`).

Questions about the project: Discord group channel (per course rules). A sp27
maintainer picking this up should start with this README, then
[docs/final_report.md](docs/final_report.md), then deploy a second region (next
step #1 above) for cross-venue data.

## License

Coursework. Not licensed for redistribution.
