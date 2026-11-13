# SFL Sign In 2.0 task context

[Station restoration and later UI corrections](layout-restoration.md) override earlier visual choices. The station/UI task completed at local commit 766d00e with Sol/Composer approvals. Preserve the original station/sidebar layout and Pi resizing, bucket-uploaded color icons with printer-sticker display_order, whole-sync Canvas UI, safe storage previews, inclusive last-month metrics, training search and compact navigation. No layout editor was requested.

[Feedback revision 3](feedback-revision-3.md), items 1–17, is authoritative over earlier council proposals and the approved local `bb81f37` baseline. Local implementation/research/testing is authorized; no push, PR, merge, production change, runner install or rollout is authorized. The user separately authorized read-only Zund inspection through the laptop on November 10. Final schema/architecture review belongs to the user. The primary coordinates ownership; delegates do not start further agents/reviews without assignment.

## Goal and evidence boundary

The user reports slow taps and unmaintainable deployed code and chose a full frontend/backend candidate. Another person's unpublished rewrite is unavailable; word-of-mouth progress does not establish its design/quality. Do not restart mediation.

Legacy repo is UNCCharlotteSuperFabLab/ManagmentSystem, with the intentional typo. Its published main baseline is not the substantially diverged Zund deployment. Newer November 7 bulk Canvas code was recovered from saved activity, not a complete production snapshot. A read-only live source/schema/aggregate snapshot was captured November 10. Full user data and media were not exported; no production importer or full migration verification is claimed. [Live comparison and migration preflight](research/zund-live-comparison.md) supersedes GitHub-only production assumptions.

The candidate is `/home/jussy/git/sfl-sign-in-v2`; scratch/review evidence is outside the repo. Do not copy private account data or credentials into docs/reviews. User explicitly authorized the configured Canvas skill token for GET-only course/catalog/submission testing, not grading, enrollment, submission or email writes. Preserve the old synthetic 8098 demo while validating the separate 8099 feedback candidate.

## Settled product direction

- pnpm/Vite/React/TanStack Router+Query and exact shadcn preset b2BpPb196. Custom admin over FastAPI/SQLModel; no Django admin/Refine/React Admin. Opus's earlier usage cap was resolved by user authorization for Sol; there is no pending lead-model permission question.
- Dense practical vertical forms/tables, human audit actor/target/action labels and record links, no recurring own-role/permission dumps. Shared Outfit typography is 24/18/16/14/12; kiosk touch controls at least 44px and responsive to Pi-sized screens. Healthy connections do not need an always-Live badge.
- Binary training completion with the original six PNGs and full-name/completion tooltips. No training tiers, definition slug/description or separate certifications UI/table.
- Anonymous occupancy names/photos/fallback and completed icons, without student/Canvas identifiers, emails or admin controls. Keep scanner/new-scan replacement, keyholder and uncertain-result behavior.
- User-entered emails only charlotte.edu/uncc.edu, case-insensitive and canonicalized once. Synthetic IDs are 80xxxxxxx; this does not outlaw other valid issued identifiers.

## Data, roles and domain services

Users contain one canonical email, nullable password_hash/avatar_key and one nullable native PostgreSQL/Python Role: superadmin/admin/operator. No viewer, accounts or user_roles table. Space level remains numeric 0/1/2/3 with a CHECK, separate from app authority. Priority minimum/default -1; later import maps every old negative to -1 and physical values 0/30/70/100 to 0/1/2/3. Mutable rows have real creation/update defaults/triggers, without fabricated imported history.

Operator reads most data/audit, assigns/revokes training and edits basic names/contact; no identity creation/import/access/priority/active/role/security changes. Admin manages domain and non-superadmin roles plus read-only SQL, without integration secrets. Superadmin manages superadmin access, passwords, object storage and supported SQL writes. Credentialed recovery-email changes remain owner/superadmin-only and cancel reset links/mail. At least one active credentialed superadmin is protected.

Shared training_types and cached canvas_quizzes remain. One trainings table combines manual awards and latest Canvas evidence. Manual owner is user_id only; Canvas owner is external_identity_id only, resolved through its canonical nullable user binding. Source CHECK/unique identity+type prevent duplicate authority/source rows. Cache can predate signup; fingerprints and binding checks protect awards. Awarded state is distinct from latest passed/score/grade. Failed/nonpassing/missing refreshes do not silently revoke accepted awards; revoked rows are not resurrected; manual rows stay independent.

Visits use enter_time/exit_time/forgot_to_sign_out only. Duration is computed; no purpose/end-quality/closure-reason taxonomy. Reports clip half-open windows, count overlapping attendance, use completed non-forgotten finalized hours/averages and first-ever new visits. JSON/CSV use one captured clock/snapshot. Timestamptz stores one instant; SQL/UI/report boundaries use America/New_York with EST/EDT, not duplicate local/UTC columns.

## Kiosk, printer, Canvas and jobs

One internal kiosk uses normal HTTP/WS with no device/pairing/intent/receipt/idempotency tables. Registration carries its identifier, new scan replaces its draft, and keyholder decisions carry expected shift. Existing volunteer opening/handoff, strictly higher-priority takeover and atomic closure remain. One in-flight command and uncertainty/refetch replace replay after lost/malformed responses.

One live printer receives ephemeral label IDs after attendance commits/responds. Offline/busy labels drop; disconnect/timeout means unknown; reconnect never prints old labels. Package original PNGs unchanged and render full names in monochrome at 1109×696 without tier defaults. No real USB output has occurred.

Every training's cached quiz selection is an assignment ID; all trainings use the recovered paginated assignment-submissions path. Retain submission ID/attempt, current evidence/fingerprint and successful start/completion diagnostics. Do not invent unsupported incremental since filters. Procrastinate handles actual Canvas/email/expiry scheduling in its jobs schema; hourly sync defaults to 3600 seconds with maintenance dispatch. No custom scheduler/run-history/mapping/result table or print queue is reintroduced.

Actual authorized reads established course 231237 Teacher access, 26 catalog assignments and submission ID/attempt. The full read-only sync succeeded after the historical roster-state fix, caching 2503 people and 14796 training rows across six training types. Fetch covers active/invited/rejected/completed/inactive and counts/skips unresolved owners without identity invention. SMTP is explicitly disabled; no real email was sent.

## SQL, storage and environments

Bundle Monaco/workers locally. Reads run immediately with no mode dropdown. Supported SA DML creates a real held transaction with before/after preview; Commit applies that exact transaction, Roll back discards it, no rerun. One per session/two globally, 90-second expiry and cleanup bound resource use. DDL, write joins, UPSERT and other unsupported forms are explicit limits. Separate restricted read/write LOGINs, parsing, output/time caps, protected account fields and atomic audit/invalidation remain; missing configuration fails closed.

Users store only an avatar key; bytes/metadata remain private S3. `/admin/storage` is a useful in-app SA object browser, not an external vendor redirect or secrets/IAM editor. List/upload/download/delete, safe attachments and referenced-avatar deletion protection are provided. API limit is 5 MiB; nginx request ceiling is 6 MiB. No S3/DB host port and no storage replacement were introduced. Storage alternatives remain research, not authority to migrate.

Use the explicit-env Compose helper. APP_PORT isolates project, volumes, network and cookie names; ports alone do not isolate browser cookies. `--dev` adds compose.dev.yaml/source mounts and Vite same-origin API/WS hot reload on the new 8099 candidate. The previous 8098 synthetic instance is preserved. CI checks/builds only; the offline legacy preflight has no apply command or target connection. Production importer/rollout remains deferred.

Pi-to-Zund migration, OneIT activation and wired subnet are resolved. Zund is host/jump box; do not recreate that backlog. Tracked old cloudflared does not establish current public exposure; current defaults omit cloudflared/Adminer and keep DB/S3 internal. The swapped-ID incident was fixed without recurrence and belongs to migration regressions. Exclude the one-off physical-button/missed-button statistics proposal.

## Handoff

Deliver current old/new schema, architecture rationale, corrected concerns, policy questions, local setup, explicit evidence limits and a fresh review of the changed snapshot. The primary owns verification-log/review-ledger updates. Feedback and station/UI reviews are complete in their own two-round series; do not substitute their approvals for new migration tooling. The station/UI checkpoint had189 backend,116 frontend,79 printer and5Compose checks. The new standalone preflight has its own backend tests and review recorded in [Status](status-report.md). Browser proof covers the SQL preview/commit/rollback, storage, audit links, role boundaries, registration, training icons and full-cache Canvas pagination; the authorized full read-only Canvas sync succeeded. User final approval remains separate.


## November 10 continuation

The user said to continue after the read-only capture. This authorizes local comparison and migration preparation, not writes to Zund. The new work is limited to a read-only source exporter, offline preflight, synthetic proof and corrected documentation. No frontend/domain/auth/schema behavior changes are needed based on the inspected bulk Canvas path. The private source export and schema must not be included in reviews without sanitization. Source account records and credential hashes were not copied. Actual import still needs explicit legacy identity, training provenance, role/password, media and cutover decisions. The captured null forgotten flags map to false by observed old reporting semantics.
