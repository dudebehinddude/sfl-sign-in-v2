# Sol architecture council, round 1

Primary reviewer: GPT-6.1 Sol. Snapshot architecture-round-1 manifest verified. Advisory decision: proceed provisionally with Vite/TanStack Router/Query, custom shadcn operator UI, FastAPI/SQLModel/PostgreSQL modular monolith and worker, durable outbox with LISTEN/NOTIFY wakeups, query-computed durations, opaque server sessions, fixed permission presets with granular grants. This is NOT final code approval or user schema approval.

## Required corrections accepted for implementation

1. Atomic lab transitions with lab/user locks, device-command scoped idempotency/input hash/result persistence, server-bound expiring registration/confirmation intents.
2. Preserve volunteer+ opening/handoff and absent keyholder+ strictly-greater priority takeover; owner alone closes directly, with others modal. No admin edit leaves active shift owner absent.
3. Per-audience transactional revision counters, not assumption that sequence IDs imply commit order. Every affected writer finalizes revision/event before commit, including SQL and worker changes.
4. LISTEN established before consistent data+revision snapshot; reconnect/listener failure resnapshot, bounded/coalesced buffers, stale REST response revision guards, private cache clear logout.
5. Canonical external identity with issuer/provider/value and nullable local binding; no second Canvas ownership binding, no silent emailalias merge. Assignment artifact kind/level/source idempotency.
6. Durable general jobs with due/state/leases/retries/dedup; expiry invalidation and printer lease/token acknowledgment, uncertain outcome does not auto-print again.
7. Explicit server permission/field/category checks, isolated kiosk/device authority, minimal public DTO, cross-process session revocation and origin/CSRF validation.
8. Actual restricted SQL connections, read-only default transaction, pglast/driver transaction-control boundary, explicit writes and samecommit invalidation; failed attempts audited outside failed transaction. Full app SQL versus DML-only provisional restriction must be disclosed for user review.
9. DB-managed updated_at, explicit retention/FKs/checks, end_time_quality, finalized-hours exclusion of open/forgotten/estimated, half-open clipped windows, first-visit newvisitor definition.
10. Instance-specific cookie names, because cookies are not isolated by port, and independent Compose data/media/networks.

## Remaining approvals

User final schema/field names/architecture/permission matrix, identity enrollment and recovery rules, certification expiry/revocation interpretation, metrics rules for estimated departures, legacy leaderboard and profile/training/invitation parity, and live Zund snapshot/migration.

The full review response is preserved in the parent task conversation; this concise implementation ledger records its actionable content without adding approval claims.
