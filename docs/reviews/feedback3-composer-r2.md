## VERDICT: APPROVE

**Snapshot:** `6be46805c1e4d3418d7449ce6fbd3d9c03d12aec790a39dd3c8e4cc0af67adf5` (base `bb81f37c0d9761c1794a73d13eddf3458c34b157`). Review used `manifest.json`, `scope-and-checks.txt`, `since-round-1.diff`, `training-review-proof.json`, `source/docs/reviews/feedback3-composer-r1.md`, `source/docs/reviews/ledger.md`, and round-2 `source/` copies only — not the live checkout, database, or private env.

### Independent review (changed code only)

`since-round-1.diff` touches behavior in `trainings.py` (`award`), `audit.py` (`ACTIONS`), four PostgreSQL regressions in `test_core.py`, and status/docs. No schema, Canvas locks/queues, or rejected-scope surfaces were reintroduced.

**S1 correction:** `award` calls `lock_user` (row-level `SELECT … FOR UPDATE` on `users`) before the duplicate probe and insert, so check+insert for the same person serializes with other identity mutations. The duplicate query matches the round-1 minimal fix: same `user_id` + `training_type_id`, `source == "manual"`, `revoked_at IS NULL`, `awarded_at IS NOT NULL`, and active via `expires_at IS NULL OR expires_at > now`, returning **409** with a clear message. Canvas rows stay outside this predicate (`training_owner_source` / `canvas_training_unique` unchanged). Revoke → reassign and expire → new assign remain allowed; regressions encode those paths.

**N1 correction:** `database.query.rolled_back` maps to `"Rolled back SQL preview"` in `ACTIONS`; `readable_audits` supplies `action_label` to the API/UI (`audit.tsx` consumes it). Emitter in `sqlpreviews.py` unchanged and still aligned.

**N2:** Unchanged frontend client-side paging on the six-type catalog; still declined as out of scope for this correction.

### Prior finding dispositions

| ID | Round-1 | Round-2 |
| --- | --- | --- |
| **S1** | should — open | **resolved** |
| **N1** | nit — open | **resolved** |
| **N2** | nit — open | **still open (declined, not gating)** |

No new in-scope blocker or should findings in the changed delta.

### Supplied evidence (not independently re-run)

Per `scope-and-checks.txt` / ledger: **156** backend tests (host Python 3.14 **22.19s**, Python 3.13 image **23.03s**), Ruff clean, unchanged **82** frontend / **47** printer / **5** Compose proofs; rebuilt **8099** HTTP checks in `training-review-proof.json` (duplicate **409**, revoke/reassign, concurrent **201**/**409**, readable rollback audit label). I did **not** re-execute those suites or HTTP flows in this review.

### Context / non-claims

- Primary GPT-6.1 Sol **feedback revision 3 round 1** on the prior snapshot remains **pending**; that is not treated as approval.
- Round-1 **bb81f37** implementation approval does not cover the feedback-revision-3 delta.
- Production migration, Canvas/SMTP/USB, and user final schema signoff remain out of scope per brief.
