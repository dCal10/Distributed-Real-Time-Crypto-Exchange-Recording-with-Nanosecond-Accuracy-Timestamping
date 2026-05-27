# ADR-0004: Three abstractions for migration-friendly deployment

**Status:** Accepted
**Date:** 2026-04-28
**Decider(s):** Yichen, team adoption

## Context

Three things differ between the laptop development environment and the eventual cloud production deployment:

1. **Timestamp source**: laptop uses NTP-disciplined `clock_gettime`; cloud uses PTP-disciplined `clock_gettime` (Phase 3) and eventually NIC hardware timestamps via `SO_TIMESTAMPING` (Phase 4 C++ collector).
2. **Storage backend**: laptop writes Parquet to `./data/`; cloud writes to S3.
3. **Lab-tier source of truth**: laptop reads back from `./data/`; cloud reads from S3.

If these three differences leak into business logic (collectors, validators, book builders), then every cloud migration becomes a painful rewrite. Worse, the official EC2 infrastructure provisioning timeline is unknown — if we can't make progress without it, we're blocked.

## Options Considered

### Option A: Hardcode laptop paths now, refactor when EC2 arrives

- Pros: fastest first version; minimal upfront design
- Cons:
  - Migration becomes a rewrite touching every collector and pipeline module
  - Risk of code drift (laptop-only branches) if migration delays
  - Doesn't match the "do not let infra provisioning be a bottleneck" principle

### Option B: Three abstract interfaces (`TimestampSource`, `RecordSink`, `RecordSource`) with config-driven concrete selection

- Pros:
  - Migration from laptop to cloud is a config flip (`RECORDING_CONFIG=local` → `RECORDING_CONFIG=aws`), not a rewrite
  - Same code runs in both environments; less drift risk
  - Concrete swaps (e.g., adding the C++ NICHwTimestampSource) don't touch business logic
  - Empirical confidence: any teammate cloning the repo can run end-to-end immediately, regardless of whether they have AWS access
- Cons:
  - More files to navigate (interface plus N concrete classes)
  - Slight over-engineering risk if N stays small

### Option C: Use a feature flag library (e.g., environment-driven `if` branches in collectors)

- Pros: no abstraction layer, just conditionals
- Cons:
  - Conditionals proliferate as N concretes grow; quickly becomes a mess
  - Tests have to cover both branches in every module
  - Same drift risk as Option A but slightly disguised

## Decision

We chose **Option B** (three abstract interfaces selected by `RECORDING_CONFIG`).

1. The cost of three small abstract base classes is trivial (~50 LOC total).
2. The benefit is that the laptop prototype runs unchanged on cloud; teammates and graders can both run the code locally without AWS credentials.
3. The pattern is standard (Strategy / dependency injection); future contributors will recognize it without explanation.

## Consequences

- **Positive:** Phase 1 and Phase 2 work runs entirely on laptop with zero cloud spend. Phase 3 deployment is a config edit. Replacing the Python `ClockGettimeSource` with a C++ `NICHwTimestampSource` in Phase 4 is one config-line swap, not a collector rewrite.
- **Negative:** Three more directories (`collector/timestamp/`, `sinks/`, `pipeline/sources/`). Slight import-graph complexity. Stub classes that raise `NotImplementedError` exist in the repo for not-yet-implemented concretes.
- **Risks:**
  - The abstractions could be wrong in ways we don't see yet — maybe the right cut is not "timestamp + sink + source" but something else. Mitigation: keep interfaces minimal; refactor early if we hit awkwardness.
  - `NotImplementedError` stubs could be silently selected if a teammate misconfigures `RECORDING_CONFIG`. Mitigation: stubs raise loudly on first call (not at import); error messages name the offending class.
- **Reversibility:** Medium. Removing the abstractions means inlining concrete logic into collectors and pipeline modules. The codebase shape would change but the data shape (Parquet schema, S3 layout) would not.

## Related

- ADR-0002: Two-tier architecture (the abstractions are the contract between tiers)
- ADR-0005: Python prototype before C++ (`NICHwTimestampSource` is a stub of the future C++ implementation)
- `UPDATE.md` § 3 "Migration-friendly architecture"
- `collector/timestamp/`, `sinks/`, `pipeline/sources/`
- `.planning/quick/1-scaffold-repo-and-abstractions/1-SUMMARY.md`
