# ADR-0011: Drop PTP-vs-NTP comparison from v1 deliverables

**Status:** Accepted
**Date:** 2026-05-08
**Decider(s):** Yichen

## Context

The original proposal (`docs/proposal.md` sections 6, 8, and 10) made the PTP-vs-NTP precision comparison a core analytical deliverable. The mechanism: capture both a PTP-disciplined timestamp and an NTP-disciplined timestamp on every record, then demonstrate in the writeup where NTP-level uncertainty degrades the cross-venue consolidated book reconstruction.

This deliverable carries two engineering implications heavier than they first appear:

1. **Infra cost.** Producing the comparison properly requires either parallel NTP-only EC2 instances per region (5 regions = 5 extra instances) or running both NTP and PTP daemons on the same instance and capturing both timestamps per message. The shared-host path is workable but operationally awkward and prone to subtle clock drift between the two disciplines.
2. **Schema surface.** The `t_ntp` field on `Timestamps` (`collector/timestamp/base.py`) is captured by every `TimestampSource` subclass on every record. On the laptop dev path it duplicates `t_userspace`. Future contributors will reasonably ask "what is this for", and the honest answer is "a deliverable we are not actually building".

The analysis is not on the critical path for the project's core contribution. Per-venue feed-latency characterization at PTP precision, the cross-venue consolidated book, and the multi-packet reassembly profiles are all fully achievable with PTP-disciplined timestamps alone. PTP-vs-NTP was a "demonstrate PTP's value" rhetorical anchor, not a measurement that informs the cross-venue analysis.

## Options Considered

### Option A: Keep the deliverable, build parallel NTP-only infra

- Pros: full original scope; strongest "PTP is worth it" demonstration in the writeup
- Cons:
  - 5x extra instances (or shared-host complexity) for what is effectively a sidebar to the main contribution
  - Adds work to a semester project that is already cost-constrained on engineering time
  - Diverts attention from the cross-venue analysis that is the actual contribution

### Option B: Keep `t_ntp` in the schema but defer the analysis to "v2 if time permits"

- Pros: zero code change; field is captured for free
- Cons:
  - Schema carries a field the project does not analyze; future readers wonder why
  - "Stretch goal" framing tends to mean "never built", better to be honest about scope

### Option C: Drop the deliverable AND prune `t_ntp` from the schema

- Pros:
  - Spec, code, and CLAUDE.md tell the same story
  - Removes a project commitment that was unlikely to ship
  - Clean schema with no orphan field
- Cons:
  - Loses the "demonstrate PTP's value" rhetorical anchor in the writeup. Replacement narratives: tighter latency distributions per venue and better-resolved consolidated-book timing both implicitly demonstrate PTP's value, just less directly.
  - Re-adding the analysis later requires re-introducing the field. Cheap but not free.

## Decision

We chose **Option C** (drop deliverable, prune `t_ntp` from the schema and the three timestamp sources).

1. The PTP-vs-NTP comparison is not on the critical path for the cross-venue latency analysis. Its absence does not weaken the core contribution.
2. Producing the comparison properly is at least an extra phase of engineering work for a project that is already constrained on time.
3. Honest scope matters more than aspirational deliverables for a graded project. "We built what we said we would" is a stronger story than "we built most of what we said we would".

## Consequences

- **Positive:** Schema is leaner. Spec, CLAUDE.md, and code agree. Engineering time freed for the cross-venue analysis and the Phase 4 C++ collector.
- **Negative:** The writeup loses one of its planned analytical narratives. The remaining narratives (per-venue latency distribution, multi-packet reassembly profiles, cross-venue feed staleness in the consolidated book) still carry the project. The "PTP makes a measurable difference" rhetoric must come from those, not from a direct PTP-vs-NTP delta.
- **Risks:**
  - Future-us may want the analysis after all. Mitigation: re-adding `t_ntp` as a captured field is a few lines of code, the only irreversible piece is the spec commitment.
- **Reversibility:** High. Schema field can be re-added, analysis can be re-scoped into a v2 phase.

## Related

- ADR-0005: Python prototype before C++ HW timestamps (same pragmatic-scope spirit)
- `docs/proposal.md` § 6, § 8, § 10 (updated to remove the PTP-vs-NTP commitment)
- `UPDATE.md` § 1 schema and "Are measuring" list (updated)
- `README.md` architecture diagram (updated)
- `collector/timestamp/{base,clock_gettime_source,ptp_source}.py` (`t_ntp` field removed)
- `CHANGELOG.md` `[2026-05-08]` entry
