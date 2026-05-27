# ADR-0010: Binance dual-stream subscription (`@depth@100ms` + `@trade`)

**Status:** Accepted, supersedes ADR-0006
**Date:** 2026-05-08
**Decider(s):** Yichen

## Context

ADR-0006 chose unbatched `@depth` for Binance under the premise that `@depth` preserves sub-100ms temporal resolution while the `@depth@100ms` and `@depth@1000ms` variants coalesce updates inside a fixed window and erase that resolution.

Empirical observation on 2026-05-08 invalidated the premise. The unbatched `@depth` stream from `data-stream.binance.vision` does not push individual matching-engine events as separate WebSocket frames. Instead it batches roughly 1 Hz at the WebSocket layer, with on the order of 130 matching-engine events bundled per frame. The frame-level arrival timestamp therefore has no more sub-second resolution than `@depth@100ms` would. ADR-0006's "unbatched preserves more cadence" reasoning does not match Binance's actual fan-out behavior on this host.

Two implications:

1. `@depth` is *worse* than `@depth@100ms` for orderbook reconstruction cadence, because it gives 1 frame/sec vs 10 frames/sec at the WebSocket layer for the same content.
2. Per-event matching-engine timestamps are still recoverable, but only via the `@trade` stream, which carries the `T` field (trade matching-engine timestamp in ms) on every individual trade event. `@trade` does fan out per-event.

## Options Considered

### Option A: Keep ADR-0006 (`@depth` unbatched)

- Pros: no change required; one stream subscription
- Cons:
  - Empirically delivers 1 Hz orderbook cadence at the WS layer, the worst of the three depth variants
  - No per-event matching-engine `T` field on depth events anyway, the `E` field on `depthUpdate` is the event-time of the *last* aggregated update inside the frame regardless of batching variant
  - Premise of ADR-0006 is wrong; staying for the sake of stability is just locking in the worse choice

### Option B: Switch to `@depth@100ms` only

- Pros:
  - 10x finer WS-layer cadence than `@depth` for orderbook reconstruction
  - One stream, lowest implementation complexity
- Cons:
  - Loses per-event matching-engine timestamps entirely; orderbook events do not carry `T`, only the frame's `E`
  - Cross-venue latency decomposition (`t_nic_first - t_exchange` per event) becomes per-frame, not per-event

### Option C: Dual subscription (`@depth@100ms` + `@trade`)

- Pros:
  - 10x finer cadence than `@depth` for orderbook reconstruction (10 Hz)
  - `@trade` carries `T` on every individual trade event, recovering the per-event matching-engine timestamp Binance does not expose on depth
  - Both streams travel the same WebSocket connection (combined-stream URL), so still one TCP/TLS session, no doubled connection cost
  - Together they recover what `@depth` alone cannot: orderbook reconstruction at 10 Hz, plus per-event timing on trades for downstream latency decomposition
- Cons:
  - Two parsers in `BinanceCollector.parse()` (one per stream type, dispatched on the `stream` field of the combined-stream wrapper)
  - Higher message rate than `@depth@100ms` alone (trades add their own throughput on top)
  - Schema gets a `stream` field per record so downstream can route depth vs trade

## Decision

We chose **Option C** (dual subscription `@depth@100ms` + `@trade`).

1. The premise of ADR-0006 was empirically wrong; staying with `@depth` would lock in the worst cadence variant.
2. Per-event matching-engine timestamps are essential for the cross-venue latency-decomposition deliverable. `@trade` is the only Binance public WS feed that exposes them on a per-event basis.
3. The combined-stream URL (`/stream?streams=<a>/<b>`) is one connection, so the cost is parser dispatch, not connection overhead.

## Consequences

- **Positive:** 10 Hz orderbook reconstruction cadence (vs 1 Hz under ADR-0006). Per-event matching-engine `T` is recovered for trade events. Cross-venue latency decomposition has a real per-event signal on Binance for the first time.
- **Negative:** `parse()` must dispatch on `stream` and produce two record shapes. `payload_json` carries the venue-specific structure; downstream readers route on the `stream` field. Slightly higher write throughput on the sink.
- **Risks:**
  - The 1 Hz observation is a single-day measurement. If Binance's WS fan-out behavior is dependent on time-of-day or symbol activity, our characterization could be incomplete. Mitigation: long-running collection across a full week before drawing conclusions.
  - Dual-stream URL syntax is documented but the combined-stream wrapper format must be verified (`{stream, data}`) on every payload. Mitigation: schema check in the parser; raise on missing keys.
- **Reversibility:** High. Stream subscription is constructed in `BinanceCollector.run()`. Reverting to ADR-0006's choice is a 2-line change to the URL builder, though "reverting" means re-adopting the worse cadence and is unlikely.

## Related

- ADR-0006: Unbatched `@depth` — superseded by this ADR
- ADR-0001: `data-stream.binance.vision` endpoint (still the host)
- `collector/exchanges/binance.py` (codifies the dual-stream subscription and parser)
- `analysis/binance_data_stream_explore.ipynb` § 2 — original ADR-0006 evidence; the 2026-05-08 finding contradicts its conclusion. Worth a follow-up notebook section confirming the 1 Hz / 130-events-per-frame observation across symbols and time windows.
