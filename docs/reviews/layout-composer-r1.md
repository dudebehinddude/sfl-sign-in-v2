## VERDICT: CHANGES

Snapshot `e11fe2cf…` (base `a133323e`) matches the layout-restoration brief in the large areas: kiosk CSS grid and station structure, occupancy left sidebar with `TrainingIcon`, `display_order` + `training_type_order()` end-to-end, bucket icons + `/media`, simplified Canvas page (whole-sync checkpoint + Canvas Users), storage previews without generic upload, SQL Ctrl+Enter via Monaco `getValue()`, inclusive previous-month metrics, and server-side training-record search. Proofs and scope-and-checks align; I could not re-run the full test matrix or browser proofs in this environment (no deps in the frozen tree).

### Findings

**S1 (should)** — `source/frontend/src/routes/admin/index.tsx:124-127`

**Claim:** Admin Overview still summarizes Canvas using per-training `trainings[].status` / `last_error` counts (`… syncing`, `… with errors`). During a whole sync, `canvas_status` marks every connected type as `running` when `None in active` (`source/backend/app/services/canvas.py:767-768`), so the card can read “6 syncing” for one whole job, or “0 syncing” when only `overview.status === 'running'`. That contradicts the task’s Canvas simplification (one whole sync + genuine whole `last_success_at`; per-training diagnostics internal only; Canvas page already fixed in `page.tsx` / `page.test.tsx`).

**Minimal fix:** In `CanvasSummary`, drive copy from `status.data.overview` (e.g. running/error/idle, `last_success_at`, `last_error`) and drop per-training aggregate lines, or remove the Canvas blurb from Overview entirely.

### Additional focus (no further should/blocker)

| Area | Assessment |
|------|------------|
| Station / Pi layout | `station.css` + `kiosk/index.tsx` match legacy arrangement; proofs claim 800×480 fit. |
| Occupancy sidebar / icons | Left aside + catalog-ordered counts (`filter.ts`); icons without extra white tile in `TrainingIcon`. |
| Uploads / media | SA-only upload (`training_icons.py:66-67`); public PNG route; printer bounded fetch. |
| Admin nav | Empty “Staff dashboard” header removed (`change.diff` on `admin/route.tsx`); collapse on desktop brand, mobile trigger. |
| Canvas UI | `page.tsx` matches tests (whole sync only on page). |
| Metrics / CSV | `previousCalendarMonth`, inclusive `shiftDate(+1)` — covered by `data.test.ts`. |
| SQL | Play icon + “Preview SQL” + `Kbd`; shortcut uses model text (`sql-editor.tsx:58`). |
| Printer order / dither | Backend order + printer tests referenced in scope; legacy asset fallback retained. |

### Verification

| Check | Source |
|-------|--------|
| 189 backend / 109 frontend / 79 printer / Compose / Ruff / builds | **Supplied** (`scope-and-checks.txt`, proofs) |
| Chromium station, occupancy, admin flows | **Supplied** (proof JSON/PNG) |
| Canvas whole-sync vs per-training UI split, SQL shortcut, metrics math | **Code review** (this pass); unit tests in snapshot **not executed** (missing env) |
| Live 8099 DB, real USB/SMTP, production migration | **Missing context** (explicitly out of scope) |

### Nits (non-blocking)

- Training Types search is client-side on the full list while `GET /training-types?search=` exists (`trainings.py:52-56`) — harmless at current scale.
- Overview Canvas card still exposes per-training semantics (S1); not a nit once fixed.

**Score:** Not scored (one localized UI mismatch; otherwise aligned with brief and recorded proofs).

Implementation note: the assessment table says SA-only upload; the implemented and tested permission contract is admin plus superadmin, with operator denied. This was not a finding and does not override the user requirement.
