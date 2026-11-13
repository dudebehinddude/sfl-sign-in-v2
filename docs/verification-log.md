# Verification log

## Station restoration and follow-up UI, November9,2026

New task after committed a133323. [Layout restoration](layout-restoration.md) records all user steering and exact evidence. Current frozen code passes189 final Python3.13 backend tests/no skips in31.56seconds; backend agent host proof189/32.88seconds;109 frontend tests30files/typecheck/lint/build;79 printer tests;5Compose checks;Ruff61files;productionimage/nginx validation. Browser and S3/media integration cover the restored original station/sidebar/photos/icons and all later Canvas/storage/metrics/SQL/header/search corrections. Final live API39source hashes match. Review is pending; prior approvals do not apply to this changed source. No production/USB/email claim.


Composer station/UI round1 identified the remaining Canvas per-training count in Overview. The primary reproduced three mismatched overall-vs-individual cases failing before the fix. The card now uses the whole-sync overview only; all112frontend tests31files/typecheck/lint/build pass and actual authenticated Overview proof reads the correct whole checkpoint without individual counts. Backend189/printer79/Compose5/PythonRuff evidence is unchanged. No new schema or scheduling logic. Primary Sol round1 remains pending; focused correction review is required.

## Feedback revision 3, November 9, 2026

This is a new user-feedback task after the approved local `bb81f37` candidate. Earlier review approvals and runtime evidence below do not approve this changed behavior. User items 1–17 are recorded in feedback-revision-3.md. No production access, push, PR or deployment occurred.

Primary observed all 156 backend tests pass without skips on host Python 3.14 in 22.19 seconds and final Python 3.13 image in 23.03 seconds, using only the dedicated disposable PostgreSQL 17 fixture. One upstream Starlette/httpx warning remains. Frontend generated API types, typecheck, lint, 83 tests across 25 files and production build pass. Ruff check/format passes for all 53 Python files. Five Compose-helper tests and all 47 printer tests pass. CI now runs pytest for the full printer suite. The production frontend image also builds; Monaco is lazy/local, with its expected large-chunk warning.

Headless Chromium checked seven actual viewports from 320×480 through 1440×900. No horizontal overflow; scanner controls remain above the fold with input44/Continue56. Pi-sized 480×320 and 800×480 have no page overflow, and the registration dialog keeps actions visible at 480×320. At narrow 320×480 secondary information scrolls naturally. Shared preview reported an incorrect resize and then timed out; after these two failures the primary switched to headless Chromium with a quoted user-facing explanation.

Actual browser workflows pass: local Monaco and immediate SELECT with no mode/confirmation; SQL before/after preview invisible to other sessions; rollback; commit without resending SQL and completed result retention; horizontal SQL scrolling and column toggles/default-hidden id; private in-app S3 upload/list/download/delete; Time/named audit links; admin read-only SQL and operator basic-detail edits with access/role/SQL/storage denials; university email validation and alias canonicalization; original training PNGs with hover tooltips; full Canvas-cache server search/pagination including 1000 rows; operator training award/revoke. No page errors or external editor CDN requests were observed. Fixtures are synthetic; no real student records/screenshots were exported.

The explicitly authorized GET-only Canvas sync succeeded: 2503 cached people, 14796 latest training rows and six successful checkpoints. Twelve skipped results are two unresolved source users across six assignments, not twelve people. One is a test student; the other remains unclassified. Expanded roster states add13 completed people but do not resolve those two, so completed enrollments are not a proven root cause. Unknown owners are counted/skipped rather than invented or attached. Failed first sync was atomic. No Canvas write/grade/enrollment request occurred. Runtime interval is3600 seconds, worker running, SMTP explicitly disabled. Clicking recovery returns503 unconfigured; no email was sent. S3/PostgreSQL have no published host ports. New8099 preview is Vite hot reload, prior8098 synthetic baseline preserved.

Twenty alternating local HTTP taps with the full cache measured median13.88ms/max21.74ms. This is not a production or before/after comparison. Physical USB output, actual SMTP delivery, Zund source/database parity, production migration and backup/restore remain unverified/deferred. Final primary Sol round2 and Composer round2 approvals are recorded below; user architecture/schema approval remains separate.

Proof lives in task scratch revision-3: viewport-proof.json, browser-proof.json, final-runtime-proof.json, runtime-proof.json and live-canvas-evidence.json. Private Canvas env/raw logs are excluded from review/export. Initial browser-script failures involved hidden Monaco input targeting, safe SQL projections, viewport constraints, actual validation wording and Base UI's popup locator; the final actual interactions pass. The first Canvas fixture did expose the unresolved-owner adapter defect, which was corrected and regression-tested before the successful full sync.


### Composer round1 correction

Four targeted PostgreSQL regressions were observed failing before the correction, then passing after it. Duplicate active manual assignments now return409 using the existing user lock across check+insert; concurrent requests create exactly one row. Revoke clears completion without a hidden second active manual row; revoked/expired history can be reassigned. No Canvas/source schema change. Host and image full156-test checks pass. The rebuilt local8099 API confirms duplicate409, revoke/reassign, concurrent201/409 and readable Rolled back SQL preview audit label. Proof is revision-3/training-review-proof.json. An initial smoke-script request used /audit instead of the actual /audit-events endpoint; correcting the fixture path completed the check.

### Primary review and SQL uncertainty wording

Sol approved round1 with one nit and no blocker/should. It independently verified313 snapshot hashes, parsed44 backend Python files, and passed5 Compose/42 label checks. Its backend dependencies were unavailable and printer-client collection lacked python-dotenv, so it did not independently rerun those suites. Composer round2 approved the duplicate-training correction and readable rollback label from source; full suites/runtime remained primary-supplied evidence. No score or usage was returned.

The primary accepted Sol S1 wording nit: a successful commit with lost reply must never be followed by No changes were saved. The new frontend regression failed before and passes after the one-branch priority fix; all83 frontend tests/typecheck/lint/production build pass. Actual Chromium forwarded a real commit to completion, dropped its reply, confirmed the saved value via API, advanced the client clock beyond expiry and observed unknown wording with no retry; fixture value restored. Proof: revision-3/uncertain-commit-proof.json. The final primary focused review covers both this nit correction and the previously approved Composer changes.

### Final feedback approval

Primary Sol approved the final snapshot510fd0899e39b2aaa1412186143ce9bc67376bf39ae6011b1e720f1f558ebf35 with no remaining blocker/should. It independently verified319 manifest entries and three Python parses, traced changed callers and accepted all fixes, without rerunning the supplied full suites/runtime checks. Composer round2 already approved its training correction. No reviewer remains pending, no score/usage was returned, and Opus remains unavailable. Two rounds per reviewer. The primary checked all309 live source hashes against the final approved snapshot before recording the result. Subsequent differences are documentation only. No behavior changes or repeated tests are required after approval.

## Earlier implementation, 2026-11-09

This section supersedes the November 8 architecture and runtime claims below. The later sections preserve evidence for the earlier implementation, including pairing, persistent print queues and receipt machinery that the user subsequently asked to remove.

The primary observed **118 backend tests pass with no skips** against disposable PostgreSQL 17, both on the host and in the current Python 3.13 image. The image run used the CI origin `http://testserver` and completed in 15.97 seconds. One upstream Starlette/httpx deprecation warning remains. The suite now exercises the simplified single-kiosk/printer contract, direct Canvas training configuration, canonical email/identity values, PostgreSQL roles, S3 storage, library-managed jobs, transactional keyholder rules, restricted SQL and consistent metrics. Canvas and SMTP transports in tests are synthetic.

The primary observed frontend type checking, lint, **32 tests across 12 files**, and a production build pass. Backend/printer/scripts Ruff checks and formatting pass for 49 files. Five printer-client protocol tests and four Compose-helper tests pass. The helper tests cover distinct instance volumes/networks and encoded database credentials. A regression verifies that the actual cron parser schedules the worker dispatcher every 30 seconds rather than every second at half-hour boundaries.

### Actual local application proof

A complete Docker Compose instance runs at loopback `http://127.0.0.1:8098` using only synthetic users, training evidence and passwords. The database, MinIO API and MinIO console have no published host ports. API readiness returns 200 after database initialization. API, worker and web images built successfully. No image was published and no production service was deployed or restarted.

The primary observed headless Chromium complete these actual UI workflows through the same-origin proxy:

- Anonymous occupancy search and badge filtering, with every effective badge visible.
- Anonymous kiosk sign-in and sign-out, updating another browser over WebSocket.
- A scanner burst while an abandoned registration field is focused replaces its identity, and only the replacement visitor is registered and signed in.
- Staff login through the actual form, plus a single canonical stored email.
- Rendered Recharts metrics and a downloaded server-generated CSV.
- Selecting a cached Canvas quiz directly on a training definition and saving it.
- Executing `SELECT 42 AS answer` through the actual CodeMirror SQL editor and displaying the database result.
- Uploading a profile photo through the app into S3, followed by a live public avatar update.
- An ordinary admin receives 403 for SQL and storage; the SQL page issues no protected database request.
- A superadmin reaches and logs into the real older full MinIO console, including the object bucket, access keys, policies and identity navigation.

These browser checks reported no page errors. Mobile occupancy was inspected at 390 pixels and has a document width of 390 pixels. Synthetic screenshots and scripts are kept in the task scratch directory `revision-2`, including `browser-proof.json`, `storage-console-proof.json`, and mobile/admin screenshots. The MinIO build is the pinned April 22, 2025 source release with its complete console; this proof does not establish ongoing upstream maintenance. Alternative storage research is separate and has not changed the running app.

### Still to establish for this revision

The primary observed 24 actual HTTP/WebSocket acceptance checks pass through Compose using a simulated printer. Offline and busy labels are dropped, reconnect produces no backlog, acknowledgment changes status, and disconnect before acknowledgment preserves an unknown outcome. Public data redaction and ordinary-admin SQL/storage denial also pass. Physical USB output remains untested. The revised whole application needs a fresh implementation review; November 8 backend approval does not cover changed behavior. Actual Canvas course access, SMTP delivery, Brother USB output, live Zund parity, production migration and final user schema approval remain unverified or deferred. No production data or deployed source dump is available. Remote CI has not run because the work is local and unpushed.

## Backend milestone, 2026-11-08

The primary observed 89 passing backend tests, no skips, against disposable PostgreSQL 17 with both DATABASE_URL and TEST_DATABASE_URL configured. The same suite passed in the built Python 3.13 image, 11.44 seconds. Host virtual environment is Python 3.14. One upstream Starlette/httpx deprecation warning remains.

Tests exercise tap concurrency and retry receipts, server-bound confirmations, keyholder transitions, permission and recovery-email boundaries, CSRF, canonical identity matching, category training authority, timestamp defaults/triggers, metrics clipping/DST, public/private WebSockets, permission revocation, pending-task cleanup, printer lease uncertainty, restricted SQL roles, private audit invalidations, Canvas synchronization and bulk imports. Deterministic external transports are fixtures.

Primary observed Ruff lint and format checks pass for backend, devices/printer and scripts. The local printer package was installed with --no-deps before the CI-equivalent six unittest checks, which all pass. Four Compose-helper tests pass, including actual rendered two-port volume/network isolation and URL-encoded database credentials.

The backend Docker image built successfully with pinned requirements on Python 3.13, non-root runtime. No image was published. Image ID at this milestone is 767019bafce9. Frontend image/full-stack runtime proof remains pending.

## Running HTTP/WebSocket proof

Task-only browser-checks/http_smoke.py passed 19 checks against the current candidate API and synthetic database: anonymous public occupancy/redaction, anonymous mutation denial, admin SQL denial, metrics hours/CSV, superadmin schema/SQL reads, read-mode write rejection, paired port-scoped device cookie, tap/sign-out, committed public updates without polling, exact-key retry, input mismatch rejection and device revocation.

Twenty alternating synthetic loopback taps had median 10.81 ms and maximum 13.20 ms. The initial tap was 63.06 ms. These are small local fixtures, not a production workload or before/after Zund benchmark. No Canvas/SMTP/USB I/O occurs in the request path.

## UI and printer evidence

Exact shadcn preset b2BpPb196 independently resolved with an empty fallback list. Home and occupancy rendered in headless Chromium and were visually inspected, including all training badges and fallback photo icons. Actual kiosk pairing/tap/live removal ran after fixing a missing device.kind response field. Mobile occupancy currently overflows by 13 pixels at viewport width 390; integrated frontend verification is unfinished.

Metrics/database slice owner reports 11 focused tests and TypeScript passing; Canvas/printing owner reports 15 focused tests. Those are scoped agent results, not a passing shared frontend suite or end-to-end browser approval.

Synthetic 1109x696 label was rendered and visually inspected. Printer receipt-journal tests cover lost acknowledgment, restart, uncertain output and explicit linked reprint. No actual Brother USB output has been tested.

## Not established

Current production parity, actual Canvas course/membership behavior, real SMTP delivery, USB printing, migration compatibility, full frontend build/interactions, full Compose smoke test, and implementation review approval. The live Zund source/database/media are not available. Advisory architecture council results are not code review approval. Remote CI has not run because this work is local and unpushed.

## Composer operational corrections

Composer round 1 returned CHANGES with three should findings. The README now requires a worker alongside the API during hot reload. Readiness returns 503 until core schema and revision rows exist. Manual Canvas synchronization during a running job returns a clear 409 without creating another job. Kiosk state also reuses its occupancy query.

Primary observed all 91 backend tests pass after these changes, on both host Python 3.14 and rebuilt Python 3.13 image 759df88bcd8c. Container run took 12.18 seconds with no skips and the same single upstream deprecation warning. Ruff lint and formatting pass. Primary Sol round 1 is still pending; current behavior requires follow-up review before approval.

## Primary Sol corrections and round 2 proof

Sol round 1 returned CHANGES with a Canvas cached-evidence blocker and three should findings. Mapping edits now invalidate cached passes under the same identity lock used by cache application/attachment; attachment also rejects pre-edit evidence. Printer sockets consult current claim ownership/state before scheduling another job and preserve uncertain output after late acknowledgments. Expiry compares parsed timezone-aware instants. Report sections share one REPEATABLE READ, read-only transaction and as-of instant for JSON and CSV.

While exercising Canvas creation, primary found post-commit untyped ORM responses becoming empty objects. Explicit refresh returns saved mapping/sync/training/certification/visit data. Regression exercises returned IDs through subsequent edits and revocation.

Primary observed **100 backend tests pass**, no skips, on host Python 3.14 in 15.29 seconds and Python 3.13 image **39bb679789d9** in 15.83 seconds. The one upstream Starlette/httpx deprecation warning remains. Ruff lint/format pass. The latest running HTTP/WebSocket smoke again passed all 19 checks. Twenty synthetic loopback taps measured median 10.64 ms, maximum 12.67 ms and first tap 66.68 ms, with the same small-fixture/no-production-comparison limitations.

New regressions cover threshold/source artifact/kind/level cache invalidation and later fresh evidence, expired printer lease followed by late 403 acknowledgment and the next successfully printed job on the same socket, -05:00 expiry payload normalization, concurrent checkout between reporting queries for both JSON and CSV, and nonempty mutation responses. No real physical printing occurred.

Round 2 must review changed behavior and the resolved findings before approval. Frontend integration remains outside this milestone and still awaits a replacement lead choice after the Opus usage failure.

## Round 2 additional review

Cursor Composer 2.5 approved immutable snapshot af5c5ef616a1d2218185f6b9d7af52e877c51ef0a150fa6534f4816bbd1fc22a. It marked all eight accepted round 1/primary findings resolved and found no new blocker/should. Composer did not independently rerun tests in this round. Its optional naive-expiry-payload nit is outside current aware-timestamp writers and deferred migration. Primary Sol round 2 remains pending; no overall implementation approval is claimed yet. No behavior changed after this snapshot.

## Primary round 2 approval

GPT-6.1 Sol approved the same immutable round 2 snapshot as Composer. Sol independently verified all 87 source file hashes and both diff hashes, parsed 44 Python files and inspected regressions. It did not independently rerun database or network tests in round 2. Both reviewers marked all accepted findings resolved; no blocker/should or pending implementation reviewer remains for this milestone. No behavior changed after the approved snapshot; primary subsequently verified live non-document-context files still match its hashes.

This is backend/printer/infrastructure approval only. Frontend integration, its build/tests/browser proof, frontend/full-stack review, actual Canvas/SMTP/USB operation, user architecture/schema approval and production migration remain outstanding or deferred as described in the status report. The task-only API later exited cleanly; previous smoke results are recorded evidence, not a claim that a preview is currently running.

## Round 3 session-lifetime correction, November 9

Composer flagged request-session ownership in HTTP kiosk commands. The primary reproduced a concrete cancellation bug with an actual PostgreSQL transaction: cancelling the HTTP task closed its session before the worker finished. `test_cancelled_http_tap_keeps_its_worker_session_open` failed before the fix and passed afterward. HTTP tap/register/keyholder now create/use/close a dedicated session entirely within their database worker. This does not add device, receipt, intent or queue machinery.

Ruff checks and formatting pass. All 119 backend tests passed on the host in 14.89 seconds and in the rebuilt Python 3.13 image with no skips. Ruff and formatting pass. The rebuilt local Compose API is healthy, and actual anonymous HTTP tap-in/tap-out succeeds with occupancy restored afterward. Earlier unchanged frontend/storage/printer evidence remains scoped as above. Primary Sol round 3 remains pending; no approval of this correction is claimed. The metrics CSV nit was declined because export correctly matches the displayed/applied chart range, whose dates are explicitly labeled.

## Round 3 remaining corrections and round 4 preparation

Primary Sol returned CHANGES on snapshot `3cca0f20abb2983c6981af6ea24334e779ad955aa0c6204f85a0f40a61befb20`. The primary independently reproduced the body-read/malformed kiosk failures and the raw database password grants. Five kiosk regressions failed before the correction and pass afterward; database-role regressions likewise failed before the correction and pass afterward. The worker terminal-notification regression failed before the new status-commit bridge and passed afterward.

Current host checks: **127 backend tests** pass, no skips, in 16.80 seconds; **50 frontend tests across 15 files**, typecheck, lint and production build pass. Ruff checks/formatting pass. The final Python 3.13 image also passes all 127 tests with no skips in 15.63 seconds. The earlier intermediate 125-test run is superseded. The final running candidate rejects pending recovery-mail SQL access and omits that table and user password hashes from its catalog; ordinary user SQL still succeeds.

Actual Chromium against the rebuilt local Compose candidate passed seven additional workflows without page errors: recovery request shows real SMTP-unconfigured guidance; a synthetic server-valid token resets a password after confirmation validation; old session is rejected; the new password logs in through the form; a reused token and missing token show invalid-link guidance; an actual committed tap followed by deliberately malformed JSON displays uncertainty without crashing/replaying; and reprovisioned console roles deny password-hash read/write while safe user browsing/SQL succeeds. The recovery page sends no-referrer and removes its query token. The primary checked that the synthetic token was absent from nginx logs. No email was sent and no real external integration was exercised.

The initial browser recovery request fixture used a reserved `.invalid` domain rejected by EmailStr; correcting the disposable request email to `example.org` exercised the intended 503 state. This was a fixture correction, not an app defect. One full-test attempt omitted DATABASE_URL and stalled at the live-listener case; it was interrupted and rerun with both required database settings. The properly configured suite passed.

Current fixes require focused round 4 review under the skill's auth/state/concurrency extension. Opus remains unavailable. Neither earlier backend approvals nor the new passing checks constitute review approval of these changes.

## Round 4 additional approval

Composer approved snapshot `b060c2fdca9616fb064412cd9a823efa429fcb33b87d78c61cb6b299903f77d4` with no new findings. It traced source and supplied evidence without rerunning tests. The primary verified all 268 live snapshot hashes still matched before recording the result. Primary Sol remains pending; only documentation changed afterward.

## Primary round 4 approval

Sol approved the same snapshot as Composer, with all accepted findings resolved and no new blocker/should. It independently verified 268 source hashes, both diffs, 41 Python parses and 17 synthetic client/kiosk checks. It did not independently rerun full suites or runtime workflows. The primary verified all live behavior files still match the approved snapshot; only four review/status documents differed before recording this approval. No behavior changed after approval. User architecture/schema approval and real integrations/production work remain separate. No reviewer is pending; Opus remains unavailable.


## Station/UI final live catalog correction

Primary observed all four cached-catalog hook tests failing before correction and passing after. All116 frontend tests32files, typecheck/lint/build pass. Chromium kept occupancy mounted while a real admin training edit changed Waterjet order/icon, then observed both changes and restoration of original sticker order/art without reload. Proof live-catalog-proof.json contains aggregate flags only. Overview correction separately has three fail-before/pass-after cases and authenticated whole-status browser proof. Backend189/printer79/Compose5/Ruff evidence remains unchanged; no backend code changed for these review fixes. Primary review of the current behavior remains pending.


## Station/UI final review and image validation

Primary Sol round2 approves the final behavior with no unresolved blocker/should; Composer round2 approves its Overview correction. All331 source files match the approved snapshot before documentation updates. Final frontend image sfl-layout-frontend:verified builds. Standalone nginx -t could not resolve api; repeating on sfl-8099_default passes configuration syntax/test. This was a missing test network, not an application defect. No behavior changes followed review. No reviewer remains pending; Opus unavailable.


## November 10 offline legacy preflight

Primary observed25 focused cases and all214 backend tests in the final Python3.13 image, no skips,31.35seconds. Ruff passes53 backend files. Existing frontend/printer/Compose behavior is unchanged and not retested. A disposable PostgreSQL source proves read-only mode rejects UPDATE, REPEATABLE READ isolates a concurrent writer and no raw hashes leave the source. The actual captured schema also restored locally with synthetic rows; extra categories, null flags, assignment mismatch and duplicate identities are retained/reported. Installed inspection runs with networking disabled and read-only input mounts, exits2 for known fixture conflicts and emits no fixture student IDs/email/hash. No apply/target connection exists. Full-data import, production restore and media/password/role policies remain unverified. New review pending.


## Migration preflight review complete

Sol primary and Composer additional approve the immutable round1 tooling snapshot. No received blocker/should remains; no reviewer is pending. Sol independently exercised23 offline cases and synthetic CLI checks; full214 PostgreSQL/image/schema/network-none proof is primary evidence. Primary source comparison found documentation-only differences after review. No behavior changed after the approved snapshot. This completes local preflight preparation, not the full importer or production migration.
