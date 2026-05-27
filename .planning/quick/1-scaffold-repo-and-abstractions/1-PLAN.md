# Plan: Scaffold Repo and Abstractions

**Quick Task:** 1
**Date:** 2026-04-29
**Mode:** quick (no research, no plan-check, no verifier)
**Phase reference:** Phase 1 (Local end-to-end with Binance)

## Goal

Establish the migration-friendly architecture skeleton from UPDATE.md § 3 and § 4: directory structure, abstract interfaces (`TimestampSource`, `RecordSink`, `RecordSource`), one working concrete `ClockGettimeSource`, config-driven environment loader (`RECORDING_CONFIG`), and YAML config templates for `local` and `aws` environments.

## Scope

**In scope:**

- Top-level directories per CLAUDE.md repo conventions: `collector/`, `collector/timestamp/`, `sinks/`, `pipeline/`, `pipeline/sources/`, `tests/`, `config/`
- Abstract base classes with full type signatures and docstrings: `Collector`, `TimestampSource`, `RecordSink`, `RecordSource`
- `Timestamps` dataclass capturing the per-message timestamp tuple from proposal § 6 schema
- One working concrete implementation: `ClockGettimeSource` (~10 LOC, validates the pattern)
- Subclass-as-marker concrete: `PTPClockGettimeSource` (same impl, documents PTP assumption)
- `NotImplementedError` stubs for not-yet-built concretes: `NICHwTimestampSource`, `S3ParquetSink`, `S3ParquetSource`
- Skeleton (no business logic) `LocalParquetSink` and `LocalParquetSource` ready for the next quick task to flesh out
- Config loader (`collector/config_loader.py`) keyed on `RECORDING_CONFIG` env var
- YAML config templates: `config/exchanges.yaml`, `config/recording.local.yaml`, `config/recording.aws.yaml`
- `requirements.txt` capturing current and near-future Python deps

**Out of scope (deferred to next quick tasks):**

- Actual websocket connection logic (Binance collector is task 2)
- Actual Parquet read/write logic (LocalParquetSink fleshing-out is task 2 or 3)
- Pipeline modules (validator, book_builder, consolidated_book) — Phase 2 work
- C++ collector — Phase 4
- Infra shell scripts — Phase 3

## Tasks

1. Create directory structure
2. Write abstract interfaces with type signatures
3. Write concrete `ClockGettimeSource` implementation
4. Write stub concretes (`PTPClockGettimeSource`, `NICHwTimestampSource`, `LocalParquetSink`, `S3ParquetSink`, `LocalParquetSource`, `S3ParquetSource`)
5. Write `config_loader.py` and YAML config templates
6. Write `requirements.txt`
7. Smoke test: import `ClockGettimeSource`, `config_loader`, `RecordSink`, `RecordSource` from repo root
8. Update STATE.md with quick task row

## Requirements addressed

ARCH-01 (TimestampSource + ClockGettimeSource), ARCH-02 (RecordSink interface + LocalParquetSink skeleton), ARCH-03 (RecordSource interface + LocalParquetSource skeleton), ARCH-05 (RECORDING_CONFIG-driven env loading).

ARCH-04 (S3 implementations) is stubbed only; concrete S3 work happens in Phase 3.

## Success criteria

1. All target files exist and contain valid Python (no `SyntaxError` on import).
2. `from collector.timestamp.clock_gettime_source import ClockGettimeSource` works from the repo root.
3. `ClockGettimeSource().capture()` returns a `Timestamps` dataclass with all five timestamp fields populated.
4. `from collector.config_loader import load_config; load_config()` returns a dict from `config/recording.local.yaml`.
5. `requirements.txt` lists every package currently installed in `.venv` plus near-future deps.
