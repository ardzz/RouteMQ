# ADR-0008: Fail-Fast Logging Audit Policy

**Status:** Accepted
**Date:** 2026-05-29
**Sprint:** Sprint 06F

## Context

The original principle audit flagged silent `except` blocks across `routemq/` and `bootstrap/` as risks
under P1-9, P1-10, P1-11, and P2-18. Silent exception handling makes operational failures hard to detect
and can hide framework defects until message loss or worker drift becomes visible elsewhere.

Sprint 06A added lifecycle log mirroring, which likely covered many of the practical gaps, but the
remaining exception behavior had never been explicitly audited. RouteMQ needed a repeatable policy for
which exceptions must fail fast, which must be logged, and which may be intentionally isolated.

## Decision

Audit every `except` block in `routemq/` and `bootstrap/` and classify each block as one of three outcomes:

1. **Fix** — log at `WARNING` or higher with `exc_info=True`, preserving the original exception in the
   operator-visible record.
2. **Re-raise** — preserve the cause chain with `raise ... from` when the caller must make an explicit
   success/failure decision.
3. **Accept** — retain best-effort behavior only for cleanup, fan-out failure, or isolation paths that
   must never break business logic. Accepted blocks get an audit row and a code comment when that context
   is not obvious locally.

Hook isolation in `routemq/observability.py` is intentionally silent and out of scope for the fail-fast
audit. Observability hooks are user extension points; a hook failure must not break message handling,
queue execution, or framework lifecycle code.

## Consequences

### Positive

- Every swallow in audited runtime code has an explicit reason recorded in
  `docs/monitoring/error-handling-audit.md`.
- Operators get warning-or-better logs for failures that indicate framework or deployment problems.
- Causal re-raise preserves debugging context where control flow must stop.
- Extension hook failures remain isolated from business logic.

### Negative

- The framework now has an audit-maintenance obligation: future exception swallows must update the table
  when introduced.
- Some accepted paths remain intentionally silent or best-effort because surfacing them as hard failures
  would create worse operational behavior.
- The audit is policy evidence, not a substitute for future targeted tests around specific failure modes.

## Status

Accepted in Sprint 06F via PR #66. The audit covered 87 blocks: 9 Fix, 1 Re-raise, and 77 Accept.

## Alternatives Considered

| Alternative | Rejected because |
|---|---|
| New exception hierarchy | Over-engineering for a small framework; the immediate risk was silent handling, not exception taxonomy. |
| Fail-fast by default | Would break message handling for transient cleanup, fan-out, and extension failures that should remain isolated. |
| Leave lifecycle logging as implicit coverage | Did not provide block-by-block evidence or future maintenance rules. |

## Related

- PR #66: Sprint 06F fail-fast logging audit.
- `docs/monitoring/error-handling-audit.md`: block classification table and findings.
