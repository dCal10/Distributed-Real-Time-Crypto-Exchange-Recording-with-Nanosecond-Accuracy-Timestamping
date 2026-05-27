# ADR-0005: Python asyncio prototype before C++ HW timestamps

**Status:** Superseded by ADR-0012
**Date:** 2026-04-28
**Decider(s):** Yichen, team adoption

> **Superseded by [ADR-0012](0012-p2-path-selection.md) (2026-05-16).**
> This ADR's premise that "Python cannot access SO_TIMESTAMPING, so C++
> is required for NIC hardware timestamps" was empirically disproven: the
> Python wsproto + `ssl.MemoryBIO` raw-socket path produces nanosecond
> NIC hardware timestamps on the Tokyo production box (100% record
> coverage, verified 2026-05-16). The Python-prototype-first *sequencing*
> this ADR chose was still correct; only its "C++ needed eventually for
> HW" conclusion is overturned. Body below preserved unedited per the
> ADR immutability rule.

## Context

The proposal mandates NIC hardware timestamps via `SO_TIMESTAMPING` for the production collector. Python cannot access `SO_TIMESTAMPING` control messages on `recvmsg()` — this is the entire reason the proposal calls out a C/C++ collector. The pattern (Boost.Asio + Boost.Beast + custom timestamp-aware stream) is referenced in Group 04's prior work.

C++ collector development is the longest single lead time in the project. If we wait for it before testing anything else, we delay the entire pipeline (parsing, schema, sink, lab tier, analytics) until late in the semester.

The proposal already notes the build order at the end: "Steps 1-8 are fully portable. They run on Yichen's laptop today, on a t3.micro tomorrow, on the official M7i.large whenever it shows up — same code, different config."

## Options Considered

### Option A: Build C++ collector first, then everything else

- Pros: production-grade hot path from day one
- Cons:
  - Blocks all downstream work (parsing, sinks, lab tier, analytics) on a single hard problem
  - C++ HW timestamping has high uncertainty (kernel API, ENA driver, instance type, etc.)
  - If the C++ collector hits a snag, the whole project stalls

### Option B: Python prototype with `clock_gettime` placeholder, swap in C++ at the timestamp layer later

- Pros:
  - Entire pipeline (5 venues, parser, sink, lab tier, analytics) can be developed in parallel with C++ work
  - `clock_gettime(CLOCK_REALTIME)` on a PTP-disciplined EC2 instance gives PTP-grade timestamps without C++ at all (hardware NIC timestamps are an *additional* improvement, not the only path to PTP precision)
  - C++ becomes one swap behind a stable interface (`TimestampSource`), not a rewrite
  - Schema is identical: Python writes the same Parquet records, with `t_nic_first` and `t_nic_last` zero-filled until the C++ collector populates them
- Cons:
  - Python recv loop adds GIL and asyncio scheduler overhead vs C++; not suitable for production hot path
  - During the Python phase, our latency numbers are limited by `clock_gettime` precision (low microseconds), not NIC HW timestamps (nanoseconds). Acceptable for prototyping; not for final results.

### Option C: Build C++ and Python in parallel from day one

- Pros: production-ready faster than Option B
- Cons:
  - Doubles the workforce demand on a four-person team
  - Risk of divergence between Python and C++ implementations
  - Doesn't actually unblock the rest of the pipeline; both are starting from scratch

## Decision

We chose **Option B** (Python prototype with `clock_gettime` placeholder; C++ swap at the timestamp layer later).

1. Unblocks the rest of the pipeline immediately.
2. Architecture (per ADR-0004) makes the C++ swap a one-line config change; we do not pay a rewrite cost for the deferred work.
3. Schema is stable from day one. The lab tier and analytics modules consume Parquet files that have the same shape regardless of whether HW timestamps are populated or zero.
4. PTP-disciplined `clock_gettime` (after Phase 3 EC2 setup) gives cross-venue timestamp comparability for headline analyses, even before the C++ collector exists. HW NIC timestamps add per-message precision that matters for the *reassembly-duration* analytics (proposal § 6 ANAL-04) but not for the *cross-venue latency comparison* (ANAL-01..03).

## Consequences

- **Positive:** Phases 1-3 deliverables are achievable on a Python-only timeline. C++ work happens in Phase 4 in parallel with final analytics. If C++ slips, Phases 1-3 still ship complete.
- **Negative:** Headline numbers for proposal § 6 ANAL-04 (reassembly duration) cannot be produced until Phase 4. This is acknowledged in the methodology section.
- **Risks:**
  - The C++ collector might never get built if the team runs out of time. Mitigation: even without it, ANAL-01..03 are deliverable using PTP `clock_gettime`. Phase 4 is the last phase; if we ship through Phase 3, we still have a complete cross-venue latency study.
  - The Python prototype's scheduling jitter could be mistaken for venue-side latency. Mitigation: report `t_userspace - t_nic_first` deltas in analytics to surface scheduler overhead explicitly.
- **Reversibility:** High at the architecture level (the swap is a config line). Low at the schedule level (committing to Python first means Phases 1-3 build on Python; if we change minds in Phase 2, we have rework).

## Related

- ADR-0002: Two-tier architecture (the cloud tier is where Python-then-C++ swap happens)
- ADR-0004: Three abstractions (the `TimestampSource` interface is what makes the swap clean)
- `collector/timestamp/clock_gettime_source.py` (Python concrete)
- `collector/timestamp/ptp_source.py` (Python concrete on PTP-disciplined system)
- `collector/timestamp/nic_hw_source.py` (C++ stub; raises NotImplementedError)
- `UPDATE.md` § 1 "Pragmatic build order"
