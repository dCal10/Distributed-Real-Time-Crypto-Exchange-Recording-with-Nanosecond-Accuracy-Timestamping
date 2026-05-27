# ADR-0012: P2 path selection — NIC HW timestamps via wsproto + MemoryBIO

**Status:** Accepted, supersedes ADR-0005
**Date:** 2026-05-15 (deployment addendum 2026-05-16)
**Decider(s):** Yichen, team-wide agreement

## Context

P1 (deploy preparation + verify) shipped on 2026-05-15. The AWS ap-northeast-1
Tokyo EC2 instance is running `BinanceCollector` via systemd, recording
`btcusdt@depth@100ms` + `btcusdt@trade` + ETH equivalents, with output
syncing to `s3://group19-ptp-tokyo/` every 5 minutes. Verify-capture
`delta_ns` medians: 1.4-4.4 ms across both streams, well inside the
<50 ms median / <200 ms p99 gate. `chronyc tracking` shows
`Reference ID: PHC0` with sub-microsecond RMS offset. PTP plumbing works.

The professor framed the project's primary deliverable as "the hardware
timestamp of the NIC and all other data from the exchange" multiple times.
The PTP-disciplined userspace timestamp from `PTPClockGettimeSource`
doesn't satisfy that wording: it's stamped at `clock_gettime` return after
`ws.recv()`, which is 50-500 microseconds (sometimes more under load)
after the NIC actually saw the bytes. The clock itself is PTP-quality;
the *stamping point* is the problem.

Per-packet metadata (multi-TCP-packet WS reassembly profile, per proposal
section 6) is also structurally unavailable through the high-level
`websockets` library, which presents fully-assembled WS messages.

The Q7 spike on 2026-05-15 (run via `tests/spike_so_timestamping.py` on
the Tokyo box) tested whether the Python `websockets` library exposes the
underlying socket enough for external `recvmsg` to pull SCM_TIMESTAMPING
ancillary data:

```
OK    socket family=AF_INET fd=6
OK    setsockopt SO_TIMESTAMPING flags=0x4c
OK    3 WS frames flowed after SO_TIMESTAMPING set (no library breakage)
INFO  recvmsg would block; websockets library is buffering ahead of socket
      path (a) requires hooking above the socket; consider (b)
```

Conclusion: the `websockets` library drains ancillary data ahead of any
external consumer. Path (a) "hijack the library's socket" is blocked.
We need path (b) — own the WS framing layer ourselves.

## Options Considered

### Option (i): Hand-roll WS handshake + TLS from scratch

- Pros: full control; zero library dependencies on the hot path
- Cons:
  - 1000+ lines reinventing two well-specified protocols (TLS state
    machine, WS framing per RFC 6455)
  - High risk of subtle bugs in TLS handshake or WS masking; both
    are notoriously hard to get right
  - Not a defensible use of semester time when sans-IO alternatives exist

### Option (ii): wsproto + `ssl.MemoryBIO` + raw socket — **CHOSEN**

- Pros:
  - Leverages mature libraries for the hard parts: `wsproto` handles WS
    framing, handshake, masking, ping/pong, fragmentation; OpenSSL via
    Python's `ssl` module handles TLS state through `MemoryBIO`
  - ~300 lines net code
  - Per-packet metadata threads cleanly: `recvmsg` per chunk →
    `(t_ns, byte_count)` recorded → bytes fed to SSL → cleartext to
    wsproto. When wsproto emits a complete WS message, we already have
    every contributing packet's timestamp and size
  - Maps 1:1 onto the existing `Timestamps` dataclass shape
    (`t_nic_first`, `t_nic_last`, `packet_metadata`) that has been
    declared since day one
- Cons:
  - Layered design has more glue code than a single-library approach
  - MemoryBIO + asyncio integration is finicky; asyncio's own SSL impl
    uses MemoryBIO internally, so the pattern is proven but the manual
    handshake loop has known edge cases (renegotiation, half-open close)

### Option (iii): Defer NIC HW timestamping, ship PTPClockGettimeSource

- Pros: zero new code; Phase 5 analysis can start immediately
- Cons:
  - Doesn't satisfy the prof's stated "hardware timestamp of the NIC"
    framing
  - Userspace stamping point blurs Binance-internal latency
    decomposition with 50-500 µs of OS scheduling noise; that's
    exactly the signal we want to surface
  - Per-packet metadata is structurally unavailable
  - Defends a less ambitious thesis than the proposal commits to

### Option (iv): C++ collector with Boost.Beast (original Phase 4 plan)

- Pros:
  - Production HFT pattern; Boost.Beast cleanly exposes `next_layer()`
    for `SO_TIMESTAMPING` setsockopt
  - Code volume comparable to (ii) in absolute terms
- Cons:
  - New build system (CMake) the team hasn't been using
  - Per-arch builds: we're on m7g.medium ARM64 Graviton, so a C++
    collector needs an ARM64 build (plus x86 only if we ever add M7i)
  - Team ramp on Boost.Beast specifically
  - Loses Python introspection of collector internals during dev

## Decision

We chose **Option (ii)** — wsproto + `ssl.MemoryBIO` + raw socket — because:

1. **Delivers the prof's stated requirement at the lowest scope cost.**
   ~12 working days for one teammate is bounded and trackable. Option (iv)
   C++ has similar code volume but adds build-system burden and team
   ramp.

2. **Per-packet metadata falls out for free.** Each `recvmsg` call
   produces a `(t_ns, byte_count)` tuple at the bottom of the stack;
   when wsproto emits a complete WS message at the top of the stack,
   we already have every contributing packet's metadata. This recovers
   the multi-TCP-packet reassembly profile the proposal commits to
   delivering.

3. **The TimestampSource abstraction was designed for this shape.**
   `Timestamps` in `collector/timestamp/base.py` already declares
   `t_nic_first`, `t_nic_last`, and `packet_metadata`. P2 fills slots
   that have been waiting since the abstract layer was first sketched.
   No refactoring of the interface; pure plumbing.

4. **Tokyo PTP infrastructure is verified working.** chrony tracking
   PHC0 with sub-µs offset; delta_ns medians 1.4-4.4 ms via the
   userspace path. If clock infrastructure were broken, neither (ii)
   nor (iii) would yield clean data; we know it isn't.

## Consequences

### Positive

- Satisfies prof's NIC HW timestamp framing.
- Recovers per-packet WS message metadata (multi-TCP-packet reassembly
  profile per proposal section 6).
- `PTPClockGettimeSource` continues recording in Tokyo as the
  production baseline; P2 can be developed in parallel and switched
  on per-venue.

### Negative

- ~12-day investment from one teammate.
- More moving parts in the collector hot path (raw socket → SSL BIO →
  wsproto vs `async for msg in ws:`).
- Asyncio + SSL BIO integration is finicky; testing on the Tokyo box
  (not just laptop) is required to validate end-to-end.

### Risks

- **MemoryBIO + asyncio handshake loop edge cases.** Renegotiation,
  half-open close, partial reads. Mitigation: pattern after asyncio's
  own SSL implementation, which uses MemoryBIO internally and has
  battle-tested these paths.
- **Binance forcibly closes WS after 24 hours.** Reconnection logic
  must handle BIO + socket teardown cleanly. Mitigation: systemd
  `Restart=on-failure` already gives free retry at the process level;
  in-process reconnect can be deferred.
- **SCM_TIMESTAMPING may report zeros if NIC HW timestamping isn't
  actually active on the enX0 interface,** even after setsockopt
  succeeds. Mitigation: validate with the same spike script under
  P2 conditions; if HW stamps are zero, the kernel/NIC stack isn't
  delivering and we need to investigate ENA driver / ethtool config
  before proceeding.

### Reversibility

Medium. The Python wsproto path lives behind the `TimestampSource`
interface; if it underperforms (CPU overhead, latency floor, async
contention), swap to Option (iv) C++ Boost.Beast that writes to the
same Parquet schema. Lab tier and downstream analysis don't see the
difference. Fallback is bounded by the schema contract, not by the
collector implementation.

## Timeline

Estimated 11-12 working days for one teammate, ~2.5 weeks elapsed at
4-5 hours/day of focused work:

| Sub-task | Days |
|---|---|
| Raw socket + SO_TIMESTAMPING setup + cmsg parsing | 2 |
| MemoryBIO-based SSL handshake loop (asyncio integration) | 2 |
| wsproto integration: handshake + frame loop | 2 |
| Per-packet timestamp accumulation, wire to Timestamps dataclass | 1 |
| Schema extension (P3 — `recv_chunks` Parquet column) + sink changes | 2 |
| Tokyo-box testing + edge cases (ping/pong, fragmented, close) | 2-3 |
| **Total** | **~11-12 days** |

## Fallback

If (ii) hits an unexpected wall (MemoryBIO + asyncio integration turns
out to be intractable, or per-packet timestamps aren't exposed correctly
via the kernel TCP path even with the right socket options), fall back
to **Option (iv) C++ Boost.Beast**, NOT Option (iii).

Option (iii) "defer" is not acceptable for the v1 deliverable. The
prof's NIC HW timestamp framing is load-bearing for the writeup.

Option (iii) continues running as the production baseline in Tokyo
regardless of P2 outcome; it's the safety net that lets us experiment
on P2 without losing recording continuity.

## Deployment addendum: AWS Nitro requires the SIOCSHWTSTAMP ioctl (2026-05-16)

P2 deployed to the Tokyo box on 2026-05-16 and verified end to end: NIC
hardware timestamps populate 100% of `binance_nic` records; userspace
jitter (`t_ptp_ns - t_nic_first_ns`) is p50 153 us (depth streams) to
1.0 ms (trade streams), p99 1.4 ms (depth) to 30 ms (trade, asyncio
scheduling under burst); `avg_chunks` per message 1.01-1.20 after the
attribution fix.

The deploy uncovered a requirement not documented by AWS for the Python
SO_TIMESTAMPING path. AWS Nitro / ENA hardware supports RX hardware
timestamping, but it ships **disabled by default**. Setting the
`SO_TIMESTAMPING` socket option with `SOF_TIMESTAMPING_RX_HARDWARE` is
necessary but not sufficient: the ENA driver only attaches hardware
timestamps once RX hardware timestamping is enabled at the device level.
That toggle is driven by the `SIOCSHWTSTAMP` ioctl with
`HWTSTAMP_FILTER_ALL`, which flips RX configuration from `0` to `1` in
`/sys/class/net/<iface>/device/hw_packet_timestamping_state` (observed
interface `ens5` on the Tokyo box). Without the ioctl, `recvmsg`
ancillary data returns a zero hardware timestamp and the source silently
degrades to the software fallback.

Resolution: `infra/scripts/enable-hw-timestamping.sh` applies the ioctl
idempotently (safe to re-run, and safe on both the `binance` and
`binance_nic` services). It runs as a systemd `ExecStartPre` with the
`+` prefix so it executes as root regardless of the service user. The
script's idempotence matters because both services may start and restart
independently; running it twice is a no-op.

This is an empirical finding worth preserving: AWS documentation covers
PTP clock discipline (chrony + PHC0) and mentions SO_TIMESTAMPING in
passing, but does not state that the device-level RX-timestamping toggle
must be flipped via `SIOCSHWTSTAMP` for the Python `recvmsg` path to see
hardware stamps. Anyone reproducing this on AWS Nitro will hit the same
silent zero-timestamp degradation without it.

## Related

- **ADR-0005** "Python asyncio prototype before C++ HW timestamps"
  (**superseded by this ADR**): 0005's premise that C++ would be
  required for NIC hardware timestamps is empirically disproven. The
  Python wsproto + `ssl.MemoryBIO` path produces nanosecond NIC
  hardware timestamps on Tokyo production (100% record coverage,
  verified 2026-05-16). 0005's Python-prototype-first *sequencing* was
  correct and is retained; only its eventual-C++-for-HW conclusion is
  overturned.
- **ADR-0010** "Binance dual-stream `@depth@100ms` + `@trade`":
  The dual-stream design from 0010 carries forward into P2 unchanged.
  Per-packet HW timestamps add a new precision tier without changing
  the subscription contract.
- `collector/timestamp/base.py` — the `Timestamps` dataclass with
  `t_nic_first`, `t_nic_last`, `packet_metadata` was designed for
  this shape; P2 plumbs through fields that have been declared from
  the start.
- `tests/spike_so_timestamping.py` — the Q7 spike script. Keep for
  re-running under different conditions (different instance type,
  different region, post-kernel-update) as a quick verification.
- Tokyo verify capture 2026-05-15 — delta_ns 1.4-4.4 ms medians (P1,
  PTPClockGettimeSource path) cited above.
- Tokyo P2 verification 2026-05-16 — NIC hardware timestamps on 100% of
  records; userspace jitter p50 153 us (depth) to 1.0 ms (trade), p99
  1.4 ms (depth) to 30 ms (trade, asyncio under burst); avg_chunks
  1.01-1.20. See the Deployment addendum above.
