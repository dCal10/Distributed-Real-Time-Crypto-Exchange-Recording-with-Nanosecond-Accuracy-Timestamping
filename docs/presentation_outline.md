# Final Presentation — Slide Outline

Target: 5-7 minutes, ~10 slides, ~40 seconds each. Each slide lists title,
content bullets, the visual, and speaker notes.

---

## Slide 1 — Title

- **Content:** Project name (aws-ptp-crypto-recording); Group 19, IE421
  Spring 2026; Yichen + Arya; Prof. Lariviere
- **Visual:** Title card. Optionally a single hero number once we have it
  (e.g. "Binance Tokyo feed latency, PTP-measured: ~X ms median")
- **Speaker notes:** One sentence framing — "We built a PTP-synchronized
  pipeline to measure crypto feed latency across venues, and deployed the
  first region."

## Slide 2 — The problem

- **Content:**
  - Crypto has no SIP: no consolidated feed, no common clock
  - Each exchange self-reports time against its own clock
  - Comparing Binance vs Coinbase timestamps = comparing two untrusted clocks
- **Visual:** Two clock faces showing different times feeding into a "?"
  consolidated view
- **Speaker notes:** Establish why this is hard before showing the solution.
  The audience needs to feel the "untrusted clocks" problem.

## Slide 3 — The approach

- **Content:**
  - PTP (not NTP): sub-microsecond common reference via AWS Time Sync
  - Collectors near each matching engine, one AWS region per venue
  - Record raw + timestamp, analyze offline (prop-firm pattern)
- **Visual:** PTP vs NTP precision bar (µs vs ms), side by side
- **Speaker notes:** PTP is the enabling idea. Emphasize "for free at the OS
  level via chrony+PHC0, no special library."

## Slide 4 — Architecture

- **Content:**
  - 5 venues, 5 regions: Binance/Tokyo, Coinbase/Virginia, Kalshi/Ohio,
    Polymarket/London, OKX/HongKong
  - Two-tier: lean cloud recorders → S3 → lab analysis tier
  - Swappable timestamp source + sink, config-driven
- **Visual:** The 5-region map with venue→region pins, then the
  cloud→S3→lab data-flow arrow
- **Speaker notes:** Don't read the table; point at the map and say "one
  collector sitting next to each exchange's matching engine."

## Slide 5 — Tokyo deployment results

- **Content:**
  - Tokyo live: Binance @depth@100ms + @trade, BTC + ETH
  - delta_ns medians 1.4-4.4 ms, sub-µs chrony offset
  - systemd-managed, 5-min S3 sync
- **Visual:** delta_ns distribution chart per stream
  (`analysis/charts/delta_p50_per_stream.png` once generated)
- **Speaker notes:** This is the "it actually works in production" slide.
  Lead with the median number; it's the proof point.

## Slide 6 — Tokyo results, continued (optional, only if time)

- **Content:**
  - Hourly latency timeline: stable / drifted?
  - (E - T) Binance-internal decomposition for trades
- **Visual:** Hourly latency line chart (`analysis/charts/hourly_latency.png`)
- **Speaker notes:** Use only if running long-form (7 min). Skip for 5 min.

## Slide 7 — The @depth coalescing finding

- **Content:**
  - We assumed "unbatched @depth" = one event per message
  - Empirically: ~1 Hz flush, ~130 events bundled per frame
  - Overturned a prior decision (ADR-0006 → ADR-0010), drove dual-stream
- **Visual:** Timeline showing 130 matching-engine events collapsing into
  one WS frame with a single timestamp
- **Speaker notes:** This is the best research-story slide. Frame it as
  "the obvious assumption was wrong, and we caught it empirically."

## Slide 8 — The NIC hardware timestamp path (Q7)

- **Content:**
  - Prof's bar: hardware NIC timestamp, not userspace clock
  - Q7 spike: the `websockets` library buffers ahead of the kernel socket
  - Path forward: wsproto + MemoryBIO over a raw socket (ADR-0012)
- **Visual:** The timestamp-stamping-point stack diagram (NIC → kernel →
  SSL → library → userspace), with the buffering wall annotated
- **Speaker notes:** Honest framing — we have a PTP-disciplined baseline now;
  NIC-HW is a de-risked, mapped-out next step, not hand-waving.

## Slide 9 — Built vs future work

- **Content:**
  - Built: PTP infra, 5-venue framework, Tokyo deployed, validator, schema
  - Future: NIC-HW source (ADR-0012), more regions, consolidated book, ML
  - Why this is the right one-semester boundary
- **Visual:** Two-column done/next checklist
- **Speaker notes:** Pre-empt "why didn't you finish X" by showing the
  boundary was a deliberate, defensible scope decision.

## Slide 10 — Handoff & continuation

- **Content:**
  - Repo + ADRs make the project pick-up-able by a sp27 student
  - Next concrete task: P2 wsproto+MemoryBIO per ADR-0012
  - Open: Kalshi/Coinbase auth, cross-venue matching window (needs data)
- **Visual:** Repo structure thumbnail + "start here → ADR-0012" arrow
- **Speaker notes:** Close on the engineering-process strength: every pivot
  is a documented ADR, so the work survives the team.

---

## Timing budget (5 min version)

| Slides | Time |
|---|---|
| 1-3 (setup) | ~1:30 |
| 4 (architecture) | ~0:45 |
| 5 (Tokyo results) | ~1:00 |
| 7 (@depth finding) | ~0:50 |
| 8 (NIC-HW path) | ~0:50 |
| 9-10 (scope + handoff) | ~0:45 |
| **Total** | **~5:40** |

Slide 6 is the flex slide for the 7-minute version.

## TODO before the talk

- Generate `analysis/charts/*.png` from real Tokyo data (slides 5, 6)
- Build the timestamp-stack diagram (slide 8) — reuse the writeup §3 figure
- Build the 5-region map graphic (slide 4)
- Confirm the hero latency number for slide 1 once data is in
