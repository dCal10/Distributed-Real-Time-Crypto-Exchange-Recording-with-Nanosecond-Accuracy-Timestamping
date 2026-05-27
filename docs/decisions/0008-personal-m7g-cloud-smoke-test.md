# ADR-0008: Personal `m7g.medium` for cloud smoke testing before official infra

**Status:** Accepted
**Date:** 2026-04-29
**Decider(s):** Yichen

## Context

Course staff will provision official EC2 instances (likely M7i.large in two regions) for production recording. The provisioning timeline is unconfirmed (`docs/questions.md`). Phases 1 and 2 are fully buildable on laptop, but Phase 3 (cloud deployment + S3 + PTP) requires *some* cloud target to validate against.

Phase 3 has three concerns that must be empirically validated before we trust the official infrastructure:

1. The instance-setup script is idempotent and produces a working PTP+ENA configuration
2. `S3ParquetSink` writes Parquet shards correctly and `S3ParquetSource` reads them back from another machine
3. `RECORDING_CONFIG=aws` swaps cleanly with no code changes from the laptop version

If we wait for the official infra to test these, we discover problems on the staff-provided machines, which is the worst possible time and place to debug.

The cheapest PTP-supported instance in the Graviton family is `m7g.medium`, ~$0.0408/hour in us-east-1 (~$30/month if running 24/7).

## Options Considered

### Option A: Wait for official infra; do not deploy on personal money

- Pros: zero personal cost
- Cons:
  - Phase 3 is gated entirely on staff timeline
  - First debug pass happens on production-bound infrastructure
  - If staff infra is delayed by weeks, the team is idle on cloud-tier work

### Option B: Personal `m7g.medium` smoke test (a few hours, single instance, us-east-1 only)

- Pros:
  - Validates the deployment pipeline before official infra arrives
  - Surfaces problems (chrony config, PHC0 device permissions, ENA driver version, IAM scope) cheaply
  - Few-hour run costs <$1
  - Code is region-agnostic; multi-region deployment is mechanical once single-region is proven
- Cons:
  - Personal money on the line, even if small
  - Team accountability question: who owns the AWS account, the bucket, the credentials

### Option C: Personal `m7g.medium` sustained recording (24/7 for weeks)

- Pros: real measurement data while waiting
- Cons:
  - ~$30/month per instance; two instances ~$60/month
  - Personal money for sustained operation
  - Without C++ collector (Phase 4), the data is `clock_gettime`-only and not the project's headline result

## Decision

We chose **Option B** (single-instance smoke test on personal `m7g.medium` after Phase 2 completes; tear down after a few hours).

1. Validates Phase 3's deployment artifacts cheaply (<$1).
2. Decouples Phase 3 readiness from staff-infra timeline.
3. Does not commit to sustained spending; the smoke test is a one-shot verification.

If staff infra slips significantly past Phase 2 completion, we may upgrade this to Option C for one instance in us-east-1, accepting ~$30/month for a month or two of continuous data.

## Consequences

- **Positive:** Phase 3 work is unblocked. We discover deployment bugs on disposable infra. The architecture's "config flip migration" claim gets empirically tested before staff infra arrives.
- **Negative:** Yichen owns a personal AWS account that gets charged. Reimbursement question: deferred to professor (see `docs/questions.md` AWS budget item).
- **Risks:**
  - `m7g.medium` may not actually support the PTP HW clock as documented. Mitigation: smoke test verifies this empirically as the very first action; if it fails, step up to `m7g.large` (~$60/month).
  - ARM (Graviton) vs Intel may surprise us when C++ collector arrives in Phase 4. Mitigation: build C++ via cross-arch Docker (`linux/arm64` and `linux/amd64`) from day one.
  - Instance left running by accident → unexpected bill. Mitigation: CloudWatch billing alarm at $5; team enforces "tear down after smoke test" discipline.
- **Reversibility:** High. The smoke test is one instance, a few hours; tearing it down is one command.

## Related

- ADR-0003: Multi-region deployment (Tokyo deployment can wait until Phase 4 if Phase 3 just validates the single-region pattern)
- ADR-0005: Python prototype before C++ (smoke test runs the Python collector; C++ comes later)
- `docs/questions.md` "AWS budget / credits" entry
- `infra/instance-setup.sh` (must be idempotent across personal m7g.medium and official M7i.large)
- `.planning/ROADMAP.md` Phase 3
