# ADR-0007: GSD with `quick` mode for lighter planning workflow

**Status:** Accepted
**Date:** 2026-04-28
**Decider(s):** Yichen

## Context

We use the GSD (Get Shit Done) workflow system for project planning, captured in `.planning/`. GSD has multiple modes:

- Full workflow: spawns research, planner, plan-checker, executor, and verifier agents at each phase
- Quick mode (`/gsd:quick`): spawns planner and executor only; skips research, plan-checker, verifier

For a four-person semester project where most tasks are well-scoped (one collector at a time, one sink at a time, etc.), the full workflow's optional agents add tokens and time without adding much value. A team of senior engineers running production deployments needs that scaffolding; a course project that's still finding its scope does not.

## Options Considered

### Option A: Full GSD workflow on every task

- Pros: highest assurance per task; research and verification catch gaps
- Cons:
  - 5x agent spawns per task (research + planner + plan-checker + executor + verifier)
  - Tokens compound across the semester; could approach uneconomical for a course budget
  - Many tasks (e.g., "scaffold a directory structure") are well-defined enough that research and verification are noise

### Option B: GSD quick mode for routine work; full mode for unfamiliar phases

- Pros:
  - Quick mode for the bulk of phase implementation (collectors, sinks, etc.)
  - Full mode reserved for genuinely uncertain phases (e.g., "C++ SO_TIMESTAMPING from scratch")
  - Total token cost roughly halved over a semester
- Cons:
  - Operator must judge when to use which mode; risk of using quick mode where full would have caught gaps

### Option C: No GSD; ad-hoc planning

- Pros: zero overhead per task
- Cons:
  - Loses atomic-commit and STATE.md tracking benefits
  - No structured artifact trail for graders
  - Each contributor invents their own task tracking

## Decision

We chose **Option B** (GSD with quick mode as the default; escalate to full mode where useful).

1. Quick mode preserves the artifacts graders care about (PLAN.md, SUMMARY.md, atomic commits) while skipping the research/check/verify ceremonies that benefit production teams more than course projects.
2. The architecture is already documented (UPDATE.md, proposal); per-task research is largely redundant.
3. STATE.md's "Quick Tasks Completed" table gives a clean grading-friendly artifact list.
4. Configurable: if a task does need the full treatment, `/gsd:plan-phase` is one command away.

## Consequences

- **Positive:** Each `/gsd:quick` invocation is roughly half the token cost of a full phase plan-execute cycle. Artifacts (PLAN.md, SUMMARY.md) are still created. The ledger of work in `.planning/quick/` is auditable.
- **Negative:** No automated plan-check or verification step. Operator and reviewer must catch gaps that the optional agents would have caught.
- **Risks:**
  - A complex task gets mis-categorized as "quick" and the planner produces a thin plan; the executor follows it; nobody catches the gap until something breaks. Mitigation: when a quick task surprises us, switch to full mode and write an ADR.
  - The "Quick Tasks Completed" table in STATE.md grows long over the semester. Mitigation: that's actually fine — a long ledger is a feature for grading visibility, not a bug.
- **Reversibility:** High. Switching to full GSD is a per-command choice (`/gsd:plan-phase` instead of `/gsd:quick`). Config in `.planning/config.json` can also be flipped via `/gsd:settings`.

## Related

- `.planning/config.json` (codifies `mode: yolo, depth: quick, research: false, plan_check: false, verifier: false`)
- `.planning/STATE.md` "Quick Tasks Completed" table
- `.planning/quick/1-scaffold-repo-and-abstractions/` (first quick task example)
