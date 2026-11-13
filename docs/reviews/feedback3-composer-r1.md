## VERDICT: CHANGES

**Snapshot:** `fc0b4412dfcaee3bc05df9226bd84d20366f5d698765eab37d40da36eaa9e0ff` (base `bb81f37c0d9761c1794a73d13eddf3458c34b157`). Review used `scope-and-checks.txt`, `manifest.json`, `change.diff`, and full `source/` copies in `reviews/feedback-3-round-1` only — not the live checkout, env, logs, or database.

### Independent review (code/diff)

Feedback items 1–17 align with the diff relative to base: viewer/slug/tiers/pairing/idempotency/print-queue/mode dropdown removals; local Monaco; SQL preview/commit on one held transaction; role matrix; in-app storage; 80xxxxxxx demo seed; university email canonicalization; original six PNG icons.

Role boundaries match intent in both API and UI (operator: identity + training assign; admin: read SQL + domain; superadmin: write SQL + storage + passwords). Kiosk HTTP uses a worker-owned DB session (`kiosk.py` `_execute`). SQL preview/commit path does not re-run SQL on commit (`sqlpreviews.py`).

Rejected-scope check (snapshot only): no restored viewer role, training slug/description, kiosk fleet/idempotency, persistent print queue, or SQL read/write mode dropdown in current source.

### Supplied evidence (not re-run)

Primary-observed checks in `scope-and-checks.txt`: 152 backend tests, 82 frontend tests, CI matrix, headless browser proofs (`browser-proof.json`, `viewport-proof.json`, `final-runtime-proof.json`), aggregate Canvas sync (`live-canvas-evidence.json`, `runtime-proof.json`). This review did **not** execute those suites or browser flows.

### Missing context

No independent rerun against disposable Postgres, production Compose, real Canvas token, or SMTP/USB. Production migration, schema signoff, and storage-engine replacement remain out of scope per brief.

---

### Findings

**S1 — should**

**File:** `source/backend/app/routes/trainings.py:158-187` (`award`)

**Claim:** Operator/admin manual assign can create multiple concurrent active manual rows for the same `user_id` + `training_type_id`. Canvas rows are uniqueness-constrained (`canvas_training_unique`); manual rows are not. A second POST leaves two non-revoked awarded manuals; `badges_for_users` keeps only one badge per type (last row wins), but the trainings grid can show duplicate “Trained” rows and revoking one leaves the other active — inconsistent with binary per-type completion and normal assign/revoke workflow.

**Minimal fix:** Before insert, `409` when an existing manual row matches the user and type with `revoked_at IS NULL`, `awarded_at IS NOT NULL`, and not expired (`expires_at IS NULL OR expires_at > now()`).

**N1 — nit**

**File:** `source/backend/app/services/audit.py:18-48` (`ACTIONS`)

**Claim:** `database.query.rolled_back` (emitted from `sqlpreviews.py:337`) has no friendly label; audit falls back to generic capitalization.

**Minimal fix:** Add e.g. `"database.query.rolled_back": "Rolled back SQL preview"`.

**N2 — nit**

**File:** `source/frontend/src/routes/admin/training-types.tsx:97-135`

**Claim:** Client-side paging over the full training-type list is fine at six types; if the catalog grows past what `trainingTypesQuery` loads, the table total can drift from server truth. Low risk today.

**Minimal fix:** None required now; use server `total` if types scale materially.

---

No blocker-severity intended-case bug was found beyond **S1**. SQL Monaco/preview/grid, storage CRUD, audit links, kiosk small-viewport layout, and permission gating are consistent with the brief and supplied browser proof descriptions.

Prior round-4 approval on `bb81f37` does **not** cover this feedback-revision-3 delta; ledger records round 1 as unprepared for approval.
