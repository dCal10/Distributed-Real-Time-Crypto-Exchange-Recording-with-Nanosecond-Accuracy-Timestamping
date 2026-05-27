# ADR-0003: Multi-region collector deployment

**Status:** Superseded by ADR-0009
**Date:** 2026-04-28
**Decider(s):** Professor Lariviere (mandate); team adoption

## Context

The project records from five venues with matching engines in different regions:

- Coinbase, Kraken, Kalshi, Polymarket — primarily US East
- Binance — Tokyo (Group 11 confirmed `ap-northeast-1a`)

Recording all five from a single AWS region (e.g., `us-east-1`) means Binance latency measurements are dominated by ~70-100ms of cross-Pacific traversal. That's a valid measurement from one vantage point, but it pollutes the per-venue latency comparison: Binance numbers reflect the network distance, not the venue's intrinsic feed behavior.

Professor's direction: collectors should be located near each exchange's matching engine. This means deploying collectors in two regions, with a region-specific config telling each instance which venues to record.

## Options Considered

### Option A: Single region (us-east-1 only)

- Pros: one deployment target, one IAM setup, one billing line
- Cons:
  - Binance numbers polluted by Pacific traversal; not a useful per-venue comparison
  - Defeats the point of the cross-venue latency analysis
  - Doesn't match prof's stated direction

### Option B: Two regions (us-east-1 + ap-northeast-1) per professor

- Pros:
  - Each collector measures latency from a clean vantage point
  - Cross-venue comparisons within a region are interpretable
  - Cross-region timestamps remain valid (both regions reference AWS atomic clock fleet, so PTP-disciplined clocks agree)
  - Matches professor's mandate
- Cons:
  - Two deploys, two billing entries, two security groups
  - Tokyo region cost slightly higher than us-east-1 (~10-15%)
  - More IaC complexity

### Option C: Three or more regions (us-east-1 + ap-northeast-1 + eu-west-1, etc.)

- Pros: more vantage points; richer cross-region analysis
- Cons:
  - Cost scales linearly per region
  - No European venue in our target list to justify EU presence
  - Adds complexity without analytical gain

## Decision

We chose **Option B** (two regions: us-east-1 for Coinbase/Kraken/Kalshi/Polymarket, ap-northeast-1 for Binance).

1. Direct professor mandate.
2. Aligns with measurement objective: each venue's latency reflects its real proximity, not artifacts of where we chose to deploy.
3. Cross-region timestamp comparison is supported by AWS PTP infrastructure (both regions use the same atomic clock fleet).

## Consequences

- **Positive:** Per-venue latency numbers are clean. Binance Tokyo is a same-region measurement; us-east-1 venues are same-region measurements. Cross-region book comparison is well-defined because clocks are PTP-disciplined to a common reference.
- **Negative:** Twice the EC2 cost. Two deploy targets to keep in sync. Cross-region S3 sync for the lab tier (or sync to a single bucket; us-east-1 is the default).
- **Risks:**
  - AWS could change PTP infrastructure such that the two regions reference different clock fleets. Mitigation: monitor `chronyc tracking` on both instances; flag drift.
  - Binance Tokyo egress could become more expensive than expected if data volume grows. Mitigation: batch Parquet shards to limit S3 PUT cost.
- **Reversibility:** Medium. Collapsing to one region requires re-deploying Binance to us-east-1 and accepting the polluted measurement. The architecture (config-driven region per collector) supports either layout.

## Related

- ADR-0002: Two-tier architecture (the cloud tier is what gets distributed across regions)
- ADR-0001: `data-stream.binance.vision` (Binance endpoint that gets accessed from `ap-northeast-1`)
- ADR-0008: Personal m7g.medium for smoke testing (initial regional deployment uses personal infra)
- `UPDATE.md` § 1 "Multi-region collector layout"
