# Composer implementation review, round 3

Reviewer: Cursor Composer 2.5. Verdict: CHANGES. Snapshot `3cca0f20abb2983c6981af6ea24334e779ad955aa0c6204f85a0f40a61befb20`. Base `a36581f0aa7b2b9de4c6ad1aebd0636646f031da`.

- **S1, should:** HTTP kiosk `perform()` passed the request-owned SQLModel session into `asyncio.to_thread`, unlike the WebSocket helper that creates its own session inside the worker. Reviewer requested a dedicated worker-owned session. The primary reproduced a concrete cancellation failure: request teardown closes the worker's transaction while it is still running. Overlapping separate requests sharing a session was not reproduced and is not needed to justify the correction. Fixed by creating, using and closing the session inside the worker; tap/register/keyholder no longer inject a request session. The new HTTP cancellation regression failed before the fix and passed after it.
- **N1, nit:** CSV export uses the last loaded metrics range rather than unapplied draft form dates. Declined: the displayed chart range is explicitly labeled, dates require Apply, and the export intentionally matches the displayed data. Exporting draft filters would instead differ from the charts.

Reviewer independently read the briefs/manifest, traced kiosk/admin/live/printing/metrics/storage contracts and sampled the large diffs. It did not rerun the primary's 118 PostgreSQL tests, 32 frontend tests, browser or printer checks. No score or usage was returned. Physical integrations and production remain outside the reviewed scope.

This was not approval. Primary Sol round 3 is still pending; the corrected session lifetime requires follow-up review. The review skill permits a state/concurrency extension while this substantive should remains open for verification.
