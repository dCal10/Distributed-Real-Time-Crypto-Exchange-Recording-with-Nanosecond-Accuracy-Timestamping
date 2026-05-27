# ADR-0009: True 5-region collector deployment

**Status:** Accepted, supersedes ADR-0003
**Date:** 2026-05-08
**Decider(s):** Yichen

## Context

ADR-0003 codified a two-region layout (`us-east-1` for Coinbase / Kraken / Kalshi / Polymarket; `ap-northeast-1` for Binance), motivated by professor's "near each exchange's matching engine" mandate. Two refinements have surfaced since:

1. **Venue swap.** Kraken is being replaced by OKX. OKX is a top-3 global crypto exchange by volume and runs on Alibaba Cloud Hong Kong, not on AWS. That is genuinely interesting for the cross-venue latency story: every other target venue is either AWS-native or matches an AWS region close to the matching engine, so OKX gives a "near but not co-located" data point that is qualitatively different from the rest.
2. **Per-venue regional refinement.** The original "us-east-1 covers everything except Binance" framing was a convenience grouping, not a "near the matching engine" answer for each venue individually. Kalshi's derivatives lineage points to Chicago metro (closest AWS: `us-east-2`), and Polymarket's CLOB infra location is undocumented enough that any single US region is a guess; placing it in `eu-west-2` instead gives the deployment global geographic spread, which has analytical value for cross-region path comparison.

Cross-region timestamp validity is unchanged by either refinement. All AWS regions reference the same atomic clock fleet, so PTP-disciplined clocks remain comparable across regions.

## Options Considered

### Option A: Keep ADR-0003 as-is (two regions, Kraken in us-east-1)

- Pros: no migration work; one fewer region to provision
- Cons:
  - Loses OKX, the most analytically interesting non-AWS-native venue
  - "Coinbase + Kalshi + Polymarket all in us-east-1" is convenient but ignores that each has a different real-world location

### Option B: Three regions (us-east-1 / us-east-2 / ap-northeast-1), Kraken kept

- Pros: incremental refinement on top of ADR-0003
- Cons: still misses OKX; still treats Polymarket as a US-East venue without evidence

### Option C: Five distinct regions, Kraken to OKX

- Pros:
  - One AWS region per venue, vantage point chosen per-venue
  - OKX adds a non-AWS-native data point (Alibaba Cloud HK, "near but not co-located")
  - Geographic spread (Tokyo, N. Virginia, Hong Kong, Ohio, London) supports richer cross-region path analysis
  - Kalshi in Ohio reflects derivatives metro (Chicago) better than NYC-adjacent us-east-1
- Cons:
  - 5x EC2 cost vs ADR-0003's 2x
  - 5 deploy targets to keep in sync (still mitigated by single-AMI + per-region systemd unit pattern)
  - `eu-west-2` for Polymarket is a vantage point choice, not a co-location claim, must be honest about that in the writeup

## Decision

We chose **Option C**. Final mapping:

| Venue | AWS Region | Rationale |
|---|---|---|
| Binance Global | `ap-northeast-1` (Tokyo) | Matching engine in Tokyo, Group 11 confirmed |
| Coinbase Spot | `us-east-1` (N. Virginia) | AWS-native |
| OKX | `ap-east-1` (Hong Kong) | OKX runs on Alibaba Cloud HK; ap-east-1 is "near but not co-located" |
| Kalshi | `us-east-2` (Ohio) | Closest AWS region to Chicago metro (US derivatives matching) |
| Polymarket | `eu-west-2` (London) | London vantage point (Polymarket infra location not publicly documented) |

1. Per-venue vantage points are individually defensible. ADR-0003's "us-east-1 covers four venues" was a convenience grouping that obscured each venue's actual proximity story.
2. The OKX swap directly serves the analytical narrative. Cross-venue latency analysis is more interesting when one venue is intentionally off the AWS-native fabric.
3. The cost delta (5 instances vs 2) is bounded by the project size: BTC-USD/USDT spot on five venues is small data per instance, the bottleneck is region-count itself, not per-region scale. `m7g.medium` for personal smoke testing keeps the bill manageable until official infra arrives.

## Consequences

- **Positive:** Per-venue measurements have clean, interpretable vantage-point semantics. Geographic spread enables cross-region path-quality analysis (e.g. Tokyo-to-N.Virginia vs London-to-N.Virginia for the same venue's data through S3).
- **Negative:** 5x EC2 cost vs ADR-0003. 5 deploy targets, 5 security groups, 5 chrony configs to keep in sync. Polymarket's London placement is a vantage choice, not a colocation claim, and must be framed honestly in the writeup.
- **Risks:**
  - OKX may rate-limit or geo-block from `ap-east-1`. Mitigation: empirical verification before committing to the region; fallback to a different AWS region in Asia-Pacific if needed.
  - Kalshi in `us-east-2` rests on the inference that Kalshi's matching infra is Chicago-metro-adjacent, this is not publicly confirmed. Mitigation: question for the professor in `docs/questions.md`; fallback to `us-east-1` if NYC-adjacent turns out to be more accurate.
  - 5 instances under official infra (when professor provisions) requires confirming credit budget covers all 5 regions. Mitigation: personal `m7g.medium` smoke testing in each region first to confirm methodology, then ask for official infra.
- **Reversibility:** Medium. Any single venue's region can be changed by editing `config/exchanges.yaml` and re-deploying. Collapsing back to ADR-0003's two-region layout requires re-deploying three venues and accepting that Kraken is gone (OKX swap is the irreversible part).

## Related

- ADR-0003: Multi-region collector deployment (two-region layout) — superseded by this ADR
- ADR-0001: `data-stream.binance.vision` (Binance endpoint, unaffected)
- ADR-0008: Personal `m7g.medium` for smoke testing (now applies to 5 regions instead of 2)
- `config/exchanges.yaml` (codifies the per-venue regions)
- `CHANGELOG.md` `[2026-05-08]` entry
- Open question in `docs/questions.md`: confirm Kalshi matching engine metro
