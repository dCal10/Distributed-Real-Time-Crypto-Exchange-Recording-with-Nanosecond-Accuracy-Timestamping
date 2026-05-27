# ADR-0002: Two-tier architecture (cloud collectors + lab pipeline)

**Status:** Accepted
**Date:** 2026-04-28
**Decider(s):** Professor Lariviere (mandate); team adoption

## Context

Original proposal (`docs/proposal.md`) described a single-machine pipeline that records, validates, builds books, and analyzes — all in one place. Professor Lariviere's framing reshaped this:

> "The goal is to build a production-grade market data recording and processing pipeline — both recording in the cloud and a VM in the lab that continually accesses, copies, processes, and validates that data, just like what would be found at any prop firm."

This is a classic two-tier prop firm pattern. The cloud-tier collectors stay lean — connect, timestamp, write — and never hold business logic that could fail and lose data. The lab tier is where validation, book reconstruction, and analytics happen, with the durable Parquet files as the contract between them.

## Options Considered

### Option A: Single-tier monolith (original proposal)

- Pros: simpler ops, fewer moving parts
- Cons:
  - If the validator or book builder crashes, the collector goes with it and we lose recording continuity
  - Doesn't match the prop firm reference architecture the professor explicitly invoked
  - Co-locates compute-heavy analytics with latency-sensitive recording

### Option B: Two-tier (collectors + lab pipeline) per professor

- Pros:
  - Matches prop firm practice
  - Recording continuity is independent of analytics availability
  - Cloud tier can be hardened to "write-only" (less code, lower bug surface)
  - Lab tier can be developed and debugged without affecting live recording
  - Files-as-interface contract makes the boundary auditable
- Cons:
  - More moving parts (two tiers to deploy and monitor)
  - S3 sync latency between tiers (acceptable for batch lab work)

### Option C: Three-tier (collectors + ticker plant + lab)

- Pros: would support real-time live consumers in addition to batch lab work
- Cons:
  - Real-time consolidated book is unconfirmed scope (see `docs/questions.md`)
  - Adds a transport layer (ZMQ ticker plant) that may not be needed if batch is acceptable
  - Premature complexity for v1

## Decision

We chose **Option B** (two-tier).

1. Direct professor mandate; not negotiable for grading purposes.
2. The pattern is well-established and removes a class of "analytics broke recording" failure modes.
3. We can add a ticker plant later (Phase 4) if real-time becomes scope, without changing the cloud tier or the file-based contract.

## Consequences

- **Positive:** Recording continuity is decoupled from analytics. Lab-tier code can iterate freely without risking the collector. Clear contract (Parquet files in S3) makes the cross-tier interface auditable.
- **Negative:** S3 sync latency (seconds to minutes depending on batch size) means the lab tier always lags. Cross-tier debugging requires checking files at the boundary.
- **Risks:** The "files only" rule (no Redis, no DB) plus two tiers means we cannot do real-time joins between venues at the cloud tier. If the prof later requires real-time analytics, we must add a Phase 5 ticker plant. Mitigation: ZMQ pub/sub is already noted in the proposal as "optional later" — we can add it without re-architecting.
- **Reversibility:** Low. The two-tier structure shapes the entire roadmap (Phase 1 builds the cloud tier, Phase 3 deploys it, lab tier work spans Phases 2 and 4). Reversing would require re-merging analytics into collectors, undoing significant separation work.

## Related

- ADR-0003: Multi-region collector deployment (concretizes where the cloud tier physically lives)
- ADR-0004: Three abstractions for migration (concretizes how the contract between tiers is implemented)
- `UPDATE.md` § 1 "Project shape (per Professor Lariviere)"
- `.planning/REQUIREMENTS.md` Lab category (LAB-01, LAB-02)
