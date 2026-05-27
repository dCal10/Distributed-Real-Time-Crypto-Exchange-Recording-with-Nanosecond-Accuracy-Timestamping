# Final Project Writeup — Outline

**Status:** Outline only. Prose is written once all data lands. Each section
has: a one-paragraph synopsis of the argument, the specific data/figures to
include, and TODOs for data we do not have yet.

Source material: [docs/proposal.md](proposal.md), [UPDATE.md](../UPDATE.md),
[docs/decisions/](decisions/), [CHANGELOG.md](../CHANGELOG.md), the Tokyo
verify capture, and the Q7 spike result.

---

## Title section

- Project: aws-ptp-crypto-recording — PTP-synchronized cross-exchange market
  data recording pipeline
- IE421 High Frequency Trading, Spring 2026, Group 19
- Contributors: Yichen (yichen32), Arya (aryac5)
- Supervisor: Professor David Lariviere
- **Abstract (1 paragraph):** synopsis — crypto has no SIP; cross-venue
  timing requires a common reference clock; we built a 5-region PTP-synced
  recording pipeline, deployed Tokyo, and characterized Binance feed latency
  at PTP precision while mapping the path to NIC hardware timestamps.

## 1. Introduction & Motivation

**Synopsis:** Argues that cross-venue crypto latency analysis is structurally
hard because each exchange self-reports time against its own clock, there is
no consolidated feed (no SIP equivalent), and naive NTP timestamps carry
enough uncertainty to invert event ordering across venues. PTP gives the
common reference; this project builds the recording substrate to exploit it.

Include:

- The "no crypto SIP" framing (from proposal §1-2)
- Why nanosecond timestamping matters: a worked example of two venues whose
  true ordering flips under ~1 ms of clock uncertainty
- Scope honesty paragraph: what this delivers (measurement substrate +
  baseline) vs what a production ticker plant would (real-time consolidated
  book, fan-out, failover)

TODO:

- Concrete NTP-uncertainty-flips-ordering example needs a real number from
  multi-region data (currently only Tokyo is live)

## 2. Architecture

**Synopsis:** The two-tier split (lean cloud recorders → S3 → lab analysis
tier) mirrors prop-firm practice and decouples recording reliability from
analysis complexity. Per-region single-venue instances are justified by the
"near the matching engine" mandate and by clean individual-attribution
boundaries.

Include:

- 5-region venue→region table (from [CLAUDE.md](../CLAUDE.md) Multi-Region
  Layout): Binance/Tokyo, Coinbase/Virginia, Kalshi/Ohio, Polymarket/London,
  OKX/Hong-Kong
- The collector pattern: `Collector` ABC + swappable `TimestampSource` +
  swappable `RecordSink`, config-driven via `RECORDING_CONFIG`
- Recording vs analysis tier diagram (adapt the ASCII from README)
- Why per-region instances vs one multi-process box: matching-engine
  proximity, region-locked S3 buckets, per-teammate attribution
- Cost analysis summary — m7g.medium (~$30/mo per region, ARM Graviton,
  ~$150/mo for 5 regions) chosen as the cheapest PTP-supported path;
  M7i.large is the alternate. Include the ARM64-PTP misdiagnosis arc:
  early ENA driver/AMI/kernel-param errors led us to briefly consider
  M7i, then `phc_enable=1` resolved them and m7g.medium went to production.

TODO:

- Arya's cost-analysis numbers (m7g.medium $/month × 5 regions + S3) need to
  be pulled into a table; reference wherever Arya documented it
- The exact ENA driver version + kernel param that resolved the ARM64 PTP
  issue (chrony shows PHC0 locked on m7g.medium + AL2023 + ENA 2.16.1g +
  phc_enable=1)

## 3. PTP Infrastructure

**Synopsis:** PTP via AWS Time Sync + chrony + PHC0 gives a sub-microsecond
disciplined clock for free at the OS level, no special library. But there is
a precision ceiling: a PTP-_disciplined_ userspace timestamp is not a NIC
_hardware_ timestamp. This section frames that distinction precisely, which
is the project's central methodological honesty.

Include:

- Why PTP not NTP for cross-venue (NTP uncertainty vs PTP sub-µs)
- AWS PHC0 + chrony setup (cite [infra/README.md](../infra/README.md)
  prerequisites; the `refclock PHC /dev/ptp_ena` line)
- Empirical `chronyc tracking` output: Reference ID = PHC0, sub-µs RMS offset
- **The key distinction:** PTP-disciplined `clock_gettime` is stamped at
  userspace `recv()` return, 50-500 µs after NIC arrival. NIC HW timestamp
  (SO_TIMESTAMPING) is stamped on the wire. Frame the userspace-vs-HW
  tradeoff here, not as an afterthought.
- Q7 spike finding: the `websockets` library buffers ahead of the kernel
  socket, blocking external `recvmsg` ancillary-data access (cite ADR-0012)

### 3a. The AWS Nitro SIOCSHWTSTAMP finding (novel empirical contribution)

**Synopsis:** A genuinely novel bit of empirical work, because AWS docs are
sparse on the Python `recvmsg` path. AWS Nitro / ENA supports RX hardware
timestamping but ships it disabled; `SO_TIMESTAMPING` with
`SOF_TIMESTAMPING_RX_HARDWARE` on the socket is necessary but not sufficient.
The device-level toggle must be flipped via the `SIOCSHWTSTAMP` ioctl with
`HWTSTAMP_FILTER_ALL` (RX config `0 → 1` in
`/sys/class/net/<iface>/device/hw_packet_timestamping_state`). Without it,
`recvmsg` ancillary data returns a zero hardware timestamp and the source
silently degrades to software fallback. AWS documentation covers chrony +
PHC0 clock discipline but does not state this for the Python path; this is
worth presenting as an original finding, not a footnote.

Include:

- The symptom: `SO_TIMESTAMPING` set, socket option accepted, yet hardware
  timestamps came back zero until the ioctl was applied
- The fix: `infra/scripts/enable-hw-timestamping.sh`, idempotent, run as a
  systemd `ExecStartPre` (root via `+` prefix), safe on both services
- Verified result: NIC HW timestamps on 100% of `binance_nic` records on
  Tokyo (2026-05-16); userspace jitter p50 153 µs (depth) to 1.0 ms (trade),
  p99 1.4 ms (depth) to 30 ms (trade, asyncio under burst)
- Why it matters: anyone reproducing NIC HW timestamping in Python on AWS
  Nitro hits the same silent zero-timestamp degradation. Cite ADR-0012
  "Deployment addendum".

TODO:

- Exact `chronyc tracking` capture from the Tokyo box (RMS offset number)
- A diagram of the timestamp-stamping-point stack (NIC → kernel → SSL →
  library → userspace) annotated with where each clock reads
- The exact `ethtool -T ens5` before/after output showing RX config 0 → 1

## 4. Implementation

**Synopsis:** Walks the collector package: one ABC, five venue subclasses,
the three-timestamp record schema, and the empirical findings that shaped
design (the `@depth` coalescing surprise, the ctypes microbenchmark
surprise). Emphasizes that schema discipline across venues makes the lab
tier venue-agnostic.

Include:

- `collector/` package structure (ABC + 5 venues + timestamp + sink)
- Three-timestamp schema: `t_exchange_ns` (exchange self-report),
  `t_ptp_ns` (PTP-disciplined local), `delta_ns` (their difference), plus
  `payload_json` preserving full original message
- **Why ctypes was considered and rejected:** the ~1.8 µs/call slowdown
  finding (ctypes `clock_gettime` measurably slower than `time.time_ns()`,
  ~18x the per-call cost). Counterintuitive: "closer to the syscall" was
  slower because of ctypes marshalling overhead. `time.time_ns()` won.
- Per-venue protocol summaries (1-2 paragraphs each):
  - Binance: combined-stream `@depth@100ms` + `@trade`, ms-int timestamps
  - Coinbase: Advanced Trade `market_trades` + `ticker`, ISO-8601 strings,
    L2 needs auth (documented limitation)
  - OKX: `books` + `trades`, ms-string timestamps, subscribe-confirmation
    filtering
  - Kalshi: RSA-PSS auth scaffolded, NotImplementedError until keys land
  - Polymarket: 500-asset cap, public CLOB
- **The empirical Binance `@depth` coalescing finding (HIGHLIGHT):** the
  unbatched `@depth` stream flushes ~1 Hz with ~130 matching-engine events
  bundled per WS frame, so it preserves no more sub-second cadence than
  `@depth@100ms`. This overturned ADR-0006 and motivated the dual-stream
  design in ADR-0010. This is the marquee research finding.

TODO:

- Pull the ctypes microbenchmark numbers from wherever they were recorded
  ([collector/timestamp/ptp_source.py](../collector/timestamp/ptp_source.py)
  docstring cites ~1.8 µs/call; need the comparison baseline number)

## 5. Empirical Findings

**Synopsis:** Presents Tokyo's baseline numbers as the first real result and
the `@depth` coalescing + Q7 buffering discoveries as the methodological
findings. This section is generated by
[tools/produce_analysis_report.py](../tools/produce_analysis_report.py) once
it runs against Tokyo's accumulated data.

Include:

- Tokyo deployment results: `delta_ns` distribution per stream (4 streams:
  btc/eth × depth/trade), p25/p50/p75/p99
- Per-stream latency characteristics + hourly timeline (drift check)
- Binance `(E - T)` internal decomposition for trade events
- Q7 spike: the buffering discovery and its implication for HW timestamp
  collection in Python (drove ADR-0012)

TODO (all need the analysis script run against Tokyo data):

- delta_ns distribution charts (`analysis/charts/*.png`)
- hourly latency timeline
- (E - T) decomposition stats
- message-rate and payload-size characterization
- **Cross-venue findings: placeholder.** Needs Coinbase/OKX deployed and
  multi-region data. Currently only Tokyo/Binance is live.

## 6. What We Built vs What's Future Work

**Synopsis:** Defends the scope boundary. One semester delivers a working
PTP recording substrate, a deployed region, baseline measurements, and a
mapped path to the harder NIC-HW work — not the full production ticker
plant. Argues these boundaries are the right ones for the time available.

Include:

- Built: PTP infra (operational Tokyo), 5-venue collector framework,
  Tokyo deployment + systemd + S3 sync, lab-side validator, uniform schema,
  baseline measurements
- Future work: NIC HW timestamps via wsproto+MemoryBIO (path fully mapped
  in ADR-0012, ~12 day estimate), additional venue deployments, real-time
  consolidated book service, ML/anomaly detection
- Why the boundary is right: NIC-HW is the prof's stated bar but the Q7
  spike showed it is a genuine research spike, not a config change;
  delivering a verified baseline + a de-risked path is honest engineering

## 7. Individual Contributions

**Synopsis:** Per course individual-attribution rule, maps deliverables to
contributors via git history.

Include:

- Yichen (yichen32): infrastructure, architecture, software pipeline,
  Tokyo deployment, collector framework, schema design
- Arya (aryac5): cost analysis, instance sizing (the ARM64-PTP
  misdiagnosis and its resolution to m7g.medium), prediction
  market planning (Kalshi/Polymarket scoping)

TODO:

- Confirm contribution split with both teammates before submission; cite
  specific commit ranges / GitLab issues per person

## 8. Lessons & Findings

**Synopsis:** The four "surprises" are the intellectual core of the
writeup. Each is a case where the obvious assumption was empirically wrong.

Include:

- The `@depth` coalescing surprise: "unbatched" did not mean per-event;
  cost us ADR-0006, gained us ADR-0010
- The ctypes microbenchmark surprise: closer-to-the-syscall was 18x slower;
  faster ≠ better, measure don't assume
- The `websockets` buffering surprise (Q7): the library drains ancillary
  data ahead of any external consumer, so HW timestamps need path (b)
- The ARM64-PTP misdiagnosis: early ENA driver/AMI/kernel-param errors on
  m7g.medium read as "ARM64 doesn't support PTP" and nearly drove a switch
  to the ~2x-cost M7i. The real fix was the `phc_enable=1` kernel
  parameter; m7g.medium runs PTP fine in production. Lesson: a transient
  infra/config failure misattributed to architecture almost cost the
  project its cheapest viable path. Verify the root cause before
  re-architecting around a symptom.
- What we would do differently with more time: start the NIC-HW spike
  earlier; deploy a second region sooner to get cross-venue data

## 9. Handoff for Continuation

**Synopsis:** A sp27 student should be able to pick this up. Points at the
repo structure, the next concrete task, and the open decisions.

Include:

- Repo structure (reference [README.md](../README.md), do not duplicate)
- Where to start: P2 — wsproto+MemoryBIO NIC timestamp source per ADR-0012
- Open decisions for next maintainer: Kalshi auth keys, Coinbase L2 auth,
  cross-venue matching window (needs data), additional region deploys
- AWS sponsorship status (TODO: current state of credits/budget)

TODO:

- AWS sponsorship/credit status as of writeup date
- Confirm ADR-0012 timeline estimate still holds after any P2 progress
