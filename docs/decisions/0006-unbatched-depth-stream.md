# ADR-0006: Use unbatched `@depth` not `@depth@100ms`

**Status:** Superseded by ADR-0010
**Date:** 2026-04-28
**Decider(s):** Yichen

## Context

Binance's Spot WebSocket API offers three pacing variants for the L2 diff-depth stream:

- `<symbol>@depth` — emits a message for every individual book update at the moment the matching engine produces it
- `<symbol>@depth@100ms` — coalesces all updates inside a 100ms window into a single batched message
- `<symbol>@depth@1000ms` — coalesces at 1000ms

For trading firms running production strategies, coalescing reduces bandwidth and per-message overhead. For our project, the choice matters in a fundamentally different way: we are *measuring* per-message latency at PTP precision.

Coalescing destroys exactly the temporal resolution we want to measure. A single `@depth@100ms` frame contains the deltas from up to 100ms of activity — we cannot tell which delta arrived when. The wire timestamp we attach to that frame is the timestamp of the *last* update inside the window, with zero information about the earlier updates' arrival order.

## Options Considered

### Option A: `@depth@100ms` (coalesced, 100ms windows)

- Pros: lower message rate (~10/sec vs ~hundreds/sec); smaller bandwidth; simpler buffer management
- Cons:
  - Erases sub-100ms timing information that motivates the entire HW-timestamping investment
  - Reassembly-duration analysis (ANAL-04) becomes meaningless

### Option B: `@depth@1000ms` (coalesced, 1s windows)

- Pros: very low message rate; minimal bandwidth
- Cons: same as A but worse, plus 1-second resolution is unusable for cross-venue alignment at staleness windows of 5-50ms (BOOK-03)

### Option C: `@depth` (unbatched, real-time)

- Pros:
  - Every book change produces its own message with its own arrival timestamp
  - Preserves the full temporal resolution available
  - Reassembly-duration analysis is meaningful (each multi-packet WS message has its own `(hw_ts, byte_count)` profile)
  - Cross-venue staleness analysis at 5/10/50ms windows is supported
- Cons:
  - Higher message rate (hundreds per second for active pairs); collector parser must keep up without dropping
  - Higher bandwidth; per-shard Parquet files are larger
  - Higher CPU cost in parser hot path

## Decision

We chose **Option C** (unbatched `@depth`).

1. The project's purpose is measurement at PTP precision. Coalescing wastes the entire HW-timestamping effort.
2. Throughput is well within what a single `m7i.large` (or `m7g.medium`) can handle. Rough estimate: BTCUSDT depth at peak activity is ~500 messages/sec; a Python collector should sustain >5000/sec with room.
3. The collector hot path is the only place where per-message overhead matters; downstream Parquet shards and S3 sync handle larger volumes fine.

## Consequences

- **Positive:** Full temporal resolution preserved. Reassembly-duration analysis is feasible. Cross-venue staleness windows are meaningful. Methodology aligns with the project's measurement goal.
- **Negative:** Higher CPU and bandwidth cost. C++ collector becomes more important to validate (Python parser may bottleneck under burst load).
- **Risks:**
  - During volatile market events, the message rate could spike beyond Python's parse capacity, leading to dropped messages. Mitigation: log dropped-message counts; if measurable, accelerate C++ collector timeline.
  - Larger Parquet shards mean higher S3 cost. Mitigation: batch by time window (5s default) so shards are bounded.
- **Reversibility:** High. Stream choice is one line in `config/exchanges.yaml` (`stream: depth` vs `stream: depth@100ms`).

## Related

- ADR-0001: `data-stream.binance.vision` endpoint (where this stream is subscribed)
- `config/exchanges.yaml` (codifies `binance.stream: depth`)
- `analysis/binance_data_stream_explore.ipynb` § 2 (throughput comparison between `@depth` and `@depth@100ms`)
- Proposal § 4 design decisions section
