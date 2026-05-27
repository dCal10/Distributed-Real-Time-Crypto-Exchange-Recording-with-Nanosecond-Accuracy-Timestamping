# Architecture Decision Records (ADRs)

This directory contains the project's Architecture Decision Records. Each ADR captures one significant decision: the context that prompted it, the alternatives considered, the choice made, and the consequences (positive, negative, and risks).

## Why ADRs

Three audiences benefit:

1. **Future-us**: when revisiting a part of the system in two months, the ADR explains why the current choice was made — not just what is.
2. **Teammates**: a new contributor can read the ADR index and understand the project's design history without spelunking through commits.
3. **Professor (graders)**: ADRs make the engineering process visible. Pivots and course-corrections appear as explicit "Supersedes ADR-NNNN" entries, not silent rewrites.

## When to write one

Write an ADR when the answer to **any** of these is yes:

- Would this decision be costly to reverse later? (e.g., schema choice, library lock-in)
- Did we consider non-trivial alternatives? (e.g., picked Python over C++ for prototype)
- Does this decision affect more than one phase? (e.g., directory layout, transport protocol)
- Did empirical research drive the choice? (e.g., Binance `.vision` vs `.com` endpoint)
- Did we pivot away from a previously committed approach?

If a decision is small, local, and unlikely to be revisited (e.g., choosing `argparse` over `click` in one file), skip the ADR and just note it in the commit message or in `.planning/PROJECT.md` Key Decisions table.

## Format

Each ADR is a Markdown file named `NNNN-short-slug.md` where `NNNN` is the next available 4-digit number. Use [`template.md`](template.md) as the starting point.

## Lifecycle

ADRs are **immutable once accepted**. If an ADR turns out to be wrong, you do not edit it — you write a new ADR that supersedes it:

1. New ADR's Status: `Accepted, supersedes ADR-NNNN`
2. Old ADR's Status updated to: `Superseded by ADR-MMMM`
3. Both entries link to each other

This preserves the engineering history. The professor can read both and see the evidence of the pivot.

## Index

| ID | Title | Status | Date |
|---|---|---|---|
| [0001](0001-binance-vision-mirror.md) | Use `data-stream.binance.vision` as Binance endpoint | Accepted | 2026-04-20 |
| [0002](0002-two-tier-architecture.md) | Two-tier architecture (cloud collectors + lab pipeline) | Accepted | 2026-04-28 |
| [0003](0003-multi-region-collectors.md) | Multi-region collector deployment | Superseded by ADR-0009 | 2026-04-28 |
| [0004](0004-three-abstractions-for-migration.md) | Three abstractions for migration-friendly deployment | Accepted | 2026-04-28 |
| [0005](0005-python-prototype-before-cpp.md) | Python asyncio prototype before C++ HW timestamps | Superseded by ADR-0012 | 2026-04-28 |
| [0006](0006-unbatched-depth-stream.md) | Use unbatched `@depth` not `@depth@100ms` | Superseded by ADR-0010 | 2026-04-28 |
| [0007](0007-gsd-quick-mode.md) | GSD with `quick` mode for lighter planning workflow | Accepted | 2026-04-28 |
| [0008](0008-personal-m7g-cloud-smoke-test.md) | Personal `m7g.medium` for cloud smoke testing before official infra | Accepted | 2026-04-29 |
| [0009](0009-five-region-collector-deployment.md) | True 5-region collector deployment (supersedes ADR-0003) | Accepted | 2026-05-08 |
| [0010](0010-binance-dual-stream-depth-100ms-plus-trade.md) | Binance dual-stream subscription `@depth@100ms` + `@trade` (supersedes ADR-0006) | Accepted | 2026-05-08 |
| [0011](0011-drop-ptp-vs-ntp-comparison.md) | Drop PTP-vs-NTP comparison from v1 deliverables | Accepted | 2026-05-08 |
| [0012](0012-p2-path-selection.md) | P2 path selection — NIC HW timestamps via wsproto + MemoryBIO (supersedes ADR-0005; deployed + verified 2026-05-16) | Accepted | 2026-05-15 |

## Quick links

- [Template for new ADRs](template.md)
- [CHANGELOG.md](../../CHANGELOG.md) for the chronological view
- [UPDATE.md](../../UPDATE.md) for the current architecture-of-record
