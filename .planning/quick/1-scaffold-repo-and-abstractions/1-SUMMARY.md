# Summary: Scaffold Repo and Abstractions

**Quick Task:** 1
**Date:** 2026-04-29
**Status:** ✓ Complete (smoke test passed)

## What was built

Directory structure and abstraction skeleton per UPDATE.md § 3 and § 4. The migration-friendly architecture (`TimestampSource`, `RecordSink`, `RecordSource`) is in place; concrete implementations are stubbed where their full logic belongs to a later quick task.

## Files created

### Collector tier
- `collector/__init__.py`
- `collector/base_collector.py` — abstract `Collector` class
- `collector/config_loader.py` — `RECORDING_CONFIG` env-var driven YAML loader (ARCH-05)
- `collector/timestamp/__init__.py`
- `collector/timestamp/base.py` — `TimestampSource` ABC + `Timestamps` dataclass
- `collector/timestamp/clock_gettime_source.py` — concrete `ClockGettimeSource` (working) (ARCH-01)
- `collector/timestamp/ptp_source.py` — concrete `PTPClockGettimeSource` (subclass marker)
- `collector/timestamp/nic_hw_source.py` — `NICHwTimestampSource` stub (raises NotImplementedError)

### Storage abstractions
- `sinks/__init__.py`
- `sinks/base_sink.py` — `RecordSink` ABC (ARCH-02)
- `sinks/local_parquet_sink.py` — `LocalParquetSink` skeleton (Parquet write deferred to next task)
- `sinks/s3_parquet_sink.py` — `S3ParquetSink` stub (Phase 3) (ARCH-04 placeholder)

### Lab tier sources
- `pipeline/__init__.py`
- `pipeline/sources/__init__.py`
- `pipeline/sources/base_source.py` — `RecordSource` ABC (ARCH-03)
- `pipeline/sources/local_source.py` — `LocalParquetSource` skeleton
- `pipeline/sources/s3_source.py` — `S3ParquetSource` stub (Phase 3)

### Tests
- `tests/__init__.py`

### Config
- `config/exchanges.yaml` — venue WS endpoints and subscription configs
- `config/recording.local.yaml` — laptop-mode environment
- `config/recording.aws.yaml` — production-mode environment (uses `${S3_BUCKET}` env var)

### Project metadata
- `requirements.txt` — current and near-future Python deps

## Smoke test (passed)

```
ClockGettimeSource.capture():
  precision_label: clock_gettime(REALTIME) (NTP-disciplined)
  t_userspace:     1777421628463388000
PTPClockGettimeSource.precision_label: clock_gettime(REALTIME) (PTP-disciplined via chrony+PHC0)
NICHw stub raises NotImplementedError as expected
load_config() local: timestamp_source=clock_gettime, sink_type=local_parquet
load_config() aws:   timestamp_source=ptp_clock_gettime, sink_type=s3_parquet
load_exchanges(): venues = ['binance', 'coinbase', 'kraken', 'kalshi', 'polymarket']
LocalParquetSink stub: write/flush/close OK
LocalParquetSource stub: yields 0 records (empty as expected)

SMOKE TEST PASSED
```

## Requirements addressed

- ARCH-01 ✓ — TimestampSource interface + ClockGettimeSource concrete
- ARCH-02 ✓ — RecordSink interface + LocalParquetSink skeleton
- ARCH-03 ✓ — RecordSource interface + LocalParquetSource skeleton
- ARCH-04 (partial) — S3 stubs in place; concrete S3 work deferred to Phase 3
- ARCH-05 ✓ — config_loader.py loads YAML based on RECORDING_CONFIG env var

## Out of scope (deferred)

- Actual websocket connect / parse logic — next quick task: `binance-collector-end-to-end`
- Actual Parquet read/write — fills `LocalParquetSink.flush()` body
- `pipeline/validator.py`, `pipeline/book_builder.py`, `pipeline/consolidated_book.py` — Phase 2
- `analysis/latency_distributions.py`, `analysis/ptp_vs_ntp.py` — Phase 2 / 4
- `infra/instance-setup.sh`, `infra/ptp-setup.sh`, `infra/s3-sync.sh` — Phase 3

## Commit guidance

Per project rule, the user is the sole committer. Suggested commit:

```bash
git add collector/ sinks/ pipeline/ tests/ config/ requirements.txt \
        .planning/quick/1-scaffold-repo-and-abstractions/ \
        .planning/STATE.md
git commit -m "feat(arch): scaffold repo and migration-friendly abstractions"
```
