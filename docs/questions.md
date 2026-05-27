# Questions for Professor Lariviere

Running log of open questions to raise with the professor. Update status when asked and when answered.

## Open

### AI/ML Component

What does the professor expect for the AI/ML component of this project?

Candidates we have considered:
- Anomaly detection on the consolidated order book
- Latency prediction from packet-level features
- NLP query interface over recorded data

Implication: First pick needed to scope v1 requirements. Affects whether ML appears as a v1 phase, a stretch goal, or out of scope.

Status: Unasked.

### Real-Time vs Batch Consolidated Book

Is real-time consolidated book reconstruction (live ZMQ subscriber merging feeds as they arrive) a requirement, or is batch reconstruction from recorded Parquet files acceptable?

Implication: Real-time is significantly more engineering work. Determines whether the consolidated book is one phase or two, and whether ticker plant subscribers must run live.

Status: Unasked.

### Prediction Market Instruments

Which specific Kalshi and Polymarket contracts should we track? Any preference for event categories (sports, politics, macro)?

Implication: Until decided, Kalshi and Polymarket integrations are stubs. Some contracts trade too thinly to produce meaningful cross-venue timing data.

Status: Unasked.

### Team Task Split

How should work be divided across the four team members to satisfy the individual attribution course rule? Are phase-per-member splits acceptable, or does the professor expect finer-grained task attribution within shared phases?

Implication: Determines whether roadmap phases map one-to-one to teammates or whether phases are shared with task-level attribution in git history.

Status: Unasked.

### VM Provisioning Timeline (or proceed on personal `m7g.medium`?)

Two questions bundled, the answer to the first determines whether the second is even relevant:

1. Are course-provisioned EC2 instances (M7i.large or equivalent PTP-supported) being procured for this group, what is the expected provisioning timeline, and what is the Guacamole access procedure plus per-team-member sudo policy?
2. If timeline is unconfirmed or coverage is uncertain, is the team authorized to proceed on personal `m7g.medium` instances (~$30/month each, ~$150/month for the 5-region deployment) as the named production target, with the option to migrate to course infrastructure later?

Implication: Architecture is already a config flip between laptop, personal `m7g.medium`, and course `M7i.large`, so any answer is workable. The question is whether to commit personal infra spend now or wait.

Status: Unasked.

### Kalshi matching engine metro

Where is Kalshi's matching infrastructure physically located? We have placed the Kalshi collector in `us-east-2` (Ohio, closest AWS region to Chicago derivatives metro at CME / CBOE), but Kalshi is HQ'd in NYC and we have no direct evidence of where their match engine actually runs.

Implication: If Kalshi runs out of NYC-adjacent infrastructure, `us-east-1` is the better vantage point and our `us-east-2` placement attributes to the venue latency that is actually our deployment choice.

Status: Unasked. Surfaced by ADR-0009.

### OKX `ap-east-1` reachability and rate-limiting

OKX runs on Alibaba Cloud Hong Kong, not on AWS. We have placed our OKX collector in `ap-east-1` (AWS Hong Kong) for a "near but not co-located" vantage point, but we have not empirically confirmed:

1. AWS `ap-east-1` egress reaches `wss://ws.okx.com:8443/ws/v5/public` without geo-blocks or rate-limits
2. Connection stability is comparable to other venues over 24-hour-plus capture windows

Implication: If OKX rate-limits public WS connections from AWS HK egress, we may need a different APAC region or different OKX endpoints. Verify before committing infra spend in `ap-east-1`.

Status: Unasked. Surfaced by ADR-0009.

### Polymarket `eu-west-2` vantage point framing

We placed Polymarket's collector in `eu-west-2` (London) as a deliberate vantage choice rather than a co-location claim, since Polymarket's CLOB infrastructure location is undocumented. The London vantage gives the deployment global geographic spread (Tokyo / Virginia / Ohio / London / Hong Kong), which has analytical value.

Question: is this framing acceptable to the professor, or does the project's "near each exchange's matching engine" mandate require us to identify Polymarket's actual infra and place the collector accordingly?

Implication: If "near matching engine" is strict, Polymarket likely moves to a US region (most likely `us-east-1`) and the global geographic spread is reduced.

Status: Unasked. Surfaced by ADR-0009.

### Multi-region `data-stream.binance.vision` reachability

Does AWS egress from each of our 5 deployment regions (`ap-northeast-1`, `us-east-1`, `us-east-2`, `eu-west-2`, `ap-east-1`) reach `data-stream.binance.vision`? The 2026-04-20 confirmation was from a US residential IP and the 2026-05-08 smoke test confirmed reachability from a local US IP. AWS egress IPs live in a separate policy zone, and the `.com` host returns HTTP 451 from US, so geo-policy could be region-specific.

`ap-northeast-1` egress (where the Binance collector actually runs) is the most important to confirm.

Status: Partial. Reachability verified from a US residential IP only. Each AWS region needs empirical confirmation before launching collectors there.

### Binance `@depth` 1 Hz observation: single-day or persistent?

ADR-0010 documents the empirical 2026-05-08 observation that the unbatched `@depth` stream from `data-stream.binance.vision` flushes at roughly 1 Hz at the WebSocket layer with about 130 matching-engine events bundled per frame. This was a single-day measurement on `btcusdt@depth`.

Question: does the 1 Hz fan-out cadence persist across symbols, time-of-day, and market-volatility regimes, or is it an artifact of test conditions on 2026-05-08?

Implication: If 1 Hz is persistent, ADR-0010 (dual-stream `@depth@100ms` + `@trade`) is the right contract permanently. If fan-out cadence varies, the contract may need revision.

Action: This is team-side empirical work, not strictly a question for the professor. Run a multi-day, multi-symbol capture and characterize the WS-layer flush distribution.

Status: Unasked. Empirical follow-up scheduled.

## Closed

### Binance Global WS Access from US residential IP

Finding (2026-04-20): The primary host `wss://stream.binance.com:9443` returns HTTP 451 from a US consumer IP. Confirmed on both `btcusdt@depth@100ms` (L2) and `btcusdt@bookTicker` (L1), so the block is host-level. The documented mirror `wss://data-stream.binance.vision` works from the same IP and delivers canonical `depthUpdate` payloads with all expected fields.

Action: Collector config defaults to `data-stream.binance.vision` as the primary Binance WS endpoint (codified in ADR-0001). Re-verify from each AWS deployment region (open question above) before launching collectors.

Fallback plan (Gemini or Binance.US per proposal section 5) is downgraded from "possibly mandatory" to "only if AWS egress also gets blocked on the mirror host."

### Binance `@depth` WebSocket fan-out cadence (initial single-day finding)

Finding (2026-05-08): The unbatched `@depth` stream from `wss://data-stream.binance.vision` flushes at roughly 1 Hz at the WS layer with on the order of 130 matching-engine events bundled per frame. This invalidates ADR-0006's premise that unbatched `@depth` preserves sub-100ms cadence.

Action: ADR-0010 supersedes ADR-0006. Binance subscription is now a combined-stream `@depth@100ms` + `@trade` URL. The follow-up open question (above) is whether the 1 Hz cadence is persistent or single-day-specific.

### PTP-vs-NTP precision comparison (descoped from v1)

Decision (2026-05-08): Drop PTP-vs-NTP comparison from v1 deliverables per ADR-0011. The comparison is not on the critical path for the cross-venue latency analysis. Producing it properly requires either parallel NTP-only infra per region (5 extra instances) or shared-host complexity. Cleaner to drop the deliverable, prune the `t_ntp` schema field, and focus on the cross-venue analysis that is the actual contribution.

Action: `t_ntp` removed from `Timestamps` dataclass and the three timestamp sources. Proposal sections 6, 8, 10 updated. May be revisited as a v2 deliverable.

---

*Last updated: 2026-05-08*
