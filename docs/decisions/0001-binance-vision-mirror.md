# ADR-0001: Use `data-stream.binance.vision` as Binance endpoint

**Status:** Accepted
**Date:** 2026-04-20
**Decider(s):** Yichen, empirical evidence

## Context

The proposal lists Binance as one of five target venues, with the matching engine confirmed in Tokyo (per Group 11's prior work). When we tested connectivity from a US residential IP using the canonical Binance market-data endpoint `wss://stream.binance.com:9443`, the WebSocket handshake was rejected with HTTP 451 ("Unavailable For Legal Reasons", RFC 7725). This is a regulatory geo-block, not a generic firewall rejection.

The block extends to multiple stream paths: `@depth` (L2 diff), `@bookTicker` (L1 best bid/ask), and others. So the block is host-level, not endpoint-level.

Binance documents an alternative host `wss://data-stream.binance.vision` described as "for market data only" (no User Data Stream, no private endpoints). It is a separate hostname on a separate `.vision` TLD that Binance registered specifically for read-only public data access.

The project cannot proceed without Binance access, since Binance Tokyo is the project's primary "distant exchange" data point and central to the cross-Pacific latency analysis.

## Options Considered

### Option A: Use `data-stream.binance.vision`

- Pros:
  - Binance's own documented endpoint for public market-data access
  - Empirically works from US IPs (verified 2026-04-20)
  - Same wire format as `.com` host — canonical `depthUpdate` payloads with all expected fields (`e`, `E`, `s`, `U`, `u`, `b`, `a`)
  - Same matching engine origin (DNS resolves to AWS `ap-northeast-1` IP space, identical TCP handshake times to `.com` from same vantage point)
  - All Spot trading pairs accessible (verified across top-cap, mid-cap, lower-cap, crypto-cross, stablecoin-cross, fiat-quote tiers)
- Cons:
  - Concern: "mirror" naming might imply downstream replication with added latency. DNS evidence (both hosts on same Tokyo subnets), TCP timing (statistically indistinguishable), and Binance's own docs (calls it an "endpoint" not a "mirror") all suggest same-DC fan-out, not replication. Residual risk acknowledged but bounded by same-datacenter copy time, dwarfed by Pacific traversal.

### Option B: Route through a US-based VPN or AWS proxy

- Pros: would access `.com` directly
- Cons:
  - Violates Binance ToS on geo-restriction circumvention; academically awkward for a graded project
  - Adds VPN hop latency that contaminates measurement; could double the cross-Pacific path length if proxy is in Tokyo
  - Defeats the entire point of measuring real network conditions to Binance Tokyo
  - Operationally fragile: VPN endpoints can be blocked themselves

### Option C: Switch Binance to Bybit, Gemini, or Binance.US

- Pros: avoids geo-block entirely
- Cons:
  - Loses the "Tokyo-distant-exchange" data point that makes cross-Pacific timing analysis the project's most novel finding
  - Gemini and Binance.US are US-based, no geographic diversity
  - Bybit is Singapore-based, partial Pacific story but proposal calls Binance out specifically

## Decision

We chose **Option A** (use `data-stream.binance.vision`).

1. Empirical evidence shows the `.vision` host works from US IPs, serves identical wire format, with identical TCP/TLS handshake times to the geo-blocked `.com` host. The two are operationally equivalent for our use case.
2. Switching exchanges (Option C) would erase the project's primary cross-Pacific finding, which is precisely what the proposal's analytical contribution depends on.
3. VPN routing (Option B) adds measurement noise and ToS risk for no analytical gain.

## Consequences

- **Positive:** Binance integration becomes a routine collector implementation rather than a research blocker. Methodology stays clean (no proxy in the data path). Project's headline cross-Pacific latency finding remains intact.
- **Negative:** A residual concern that `.vision` could be a downstream replica of `.com`'s fan-out plant remains technically unverifiable from outside Binance's infrastructure. Bounded by same-datacenter copy time (sub-millisecond), but worth disclosing in the methodology section of the writeup.
- **Risks:** Binance could change geo-policy on `.vision` at any time. Mitigation: keep Bybit (Singapore) as a contingency Pacific venue if `.vision` later gets blocked.
- **Reversibility:** High. The collector's endpoint URL is one line in `config/exchanges.yaml`. Switching to Bybit (Option C) would require new collector code but the rest of the pipeline (sinks, lab tier, analytics) is venue-agnostic.

## Related

- `docs/proposal.md` § 5 (Binance notes)
- `docs/questions.md` "Binance Global WS Access from US" entry (closed by this ADR; pending verification from us-east-1 in Phase 3)
- `analysis/binance_data_stream_explore.ipynb` (empirical methodology demonstration)
- `config/exchanges.yaml` (codifies this choice as `binance.endpoint`)
