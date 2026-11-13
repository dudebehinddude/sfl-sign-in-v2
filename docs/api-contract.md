# API contract, feedback revision 3

Current [OpenAPI](../backend/openapi.json), [input schemas](../backend/app/schemas.py) and [response models](../backend/app/responses.py) define the wire contract. This implements [feedback items 1–17](feedback-revision-3.md); it is not production compatibility or final user approval.

## Conventions and authorization

FastAPI exports `app.main:app`/`create_app()`. CLI is `python -m app.cli`; worker is `python -m app.worker`. Health `GET /api/health` returns 503 before required tables/public+staff counters exist. `init-db` initializes a fresh app/library jobs schema, not an upgrade/importer.

JSON uses snake_case, UUID strings and aware ISO timestamps. Pages are `{items,total,page,page_size}`, normally default 100/cap 1000. Errors use status and `{detail}`. Each user has nullable scalar `role:superadmin|admin|operator`, without roles arrays or viewer. `space_level` remains numeric 0–3. User-entered emails accept charlotte.edu/uncc.edu case-insensitively and canonicalize aliases. Normal DTOs omit password hashes.

Operator can read most domain/audit data, edit basic names/contact fields and assign/revoke training. Operator cannot create/import identities or change access/priority/active/role/security. Admin manages domain data/non-superadmin roles and SQL reads. Superadmin controls superadmin grants, password provisioning, S3 objects and supported SQL writes. Server checks apply independently of UI visibility; integration secrets are not exposed by an admin API.

## Public projections, sessions and profile

`GET /api/public/occupancy` returns `{revision,lab:{is_open,keyholder},occupants}`. Public people are `{id,display_name,avatar_url}`; occupants add badges `{training_type_id,name,icon_key}`. There are no levels, slugs/colors, student/Canvas identifiers, emails or admin controls. `GET /api/public/training-types` returns `{items:[{id,name,icon_key}]}`. The public forgotten-signout leaderboard's audience remains a product decision.

`POST /api/auth/login {identifier,password}` and `GET /api/auth/me` return `{user:{id,display_name,email,role,permissions},csrf_token}` and an HttpOnly session cookie named by APP_PORT. Permission strings are internal authorization data, not a UI catalog. Anonymous me is 401. Staff mutations require `X-CSRF-Token`, accepted origin and current permissions. Logout is POST; password change is `POST /api/auth/password {current_password,new_password}`.

Recovery is `POST /api/auth/password-reset/request {email}` and `/complete {token,password}`. Request responses stay generic; 503 unconfigured mail/429 limits remain visible. `/recover-password` and `/reset-password?token=...` provide the UI. The reset page replaces the URL after capture; proxy recovery-page logs/referrers are suppressed. Reset revokes old sessions. Changing a credentialed recovery email requires owner/superadmin and cancels pending links/mail. No actual SMTP delivery is claimed.

`GET /api/me/profile` is `{user,total_hours,completed_visits,visits:<page>}`. Own names/email are PATCH; avatar multipart `file` is POST `/api/me/avatar`. Validated JPEG/PNG is reencoded to JPEG in the private S3 bucket; intended associated avatars are served at `/media/avatars/{key}`. Users hold avatar_key only.

## Internal kiosk and WebSockets

| HTTP route | Body/state |
| --- | --- |
| `GET /api/kiosk/state` | Occupancy, present/unique-today/weekly-hours stats and recent `{user_id,display_name,action,occurred_at}` activity; no device field. |
| `POST /api/kiosk/tap` | `{identifier}` |
| `POST /api/kiosk/register` | `{identifier,first_name,last_name,email}` |
| `POST /api/kiosk/keyholder` | `{identifier,action,expected_shift_id,target_identifier?,sign_out_current_keyholder?}` |

Results are `{status,message,user,revision,identifier?,expected_shift_id?,actions?}`. Status is signed_in/signed_out/registration_required/keyholder_action_required/lab_closed. Unknown scans create no abandoned account. Registration cannot overwrite an existing identifier. Expected shift is null to open or current UUID otherwise; stale state is 409. Volunteer+ may open/receive handoff; arriving keyholder+ override requires strictly greater priority. Continue declines an offered override.

The configured origin is required for internal commands; no pairing/device/staff session is required. Lab locking/one-open constraints make visit/shift changes atomic. One submission at a time, with refresh/uncertainty after lost, malformed or unreadable replies, replaces automatic toggle replay. Attendance commits/responds before printer dispatch; no Canvas/SMTP/USB I/O occurs inside its transaction.

| WS route | Contract |
| --- | --- |
| `/ws/public` | `{type:snapshot,topic:occupancy,revision,data}` initially and on changes. |
| `/ws/admin` | Staff cookie/origin; `{type:invalidate,topics,revision}`; session/role rechecked before private updates. |
| `/ws/kiosk` | Occupancy plus `{type:command,id,command:tap|register|keyholder,data}` and matching result/error envelope. |
| `/ws/printer` | One internal subscriber; server `{type:label,id,label:{display_name,avatar_url?,badges}}`; client `{type:ack,id,status:printed|failed|unknown,error?}`. Badge fields match the public binary badge DTO. |

Ping/pong is supported. Public/staff counters lock through commit; NOTIFY carries topics, not private rows. Listener registration precedes a consistent snapshot; reconnect resnapshots. No device/intent/receipt/change-log/print-queue tables or offline mutation replay are implied.

## People, definitions, trainings and audit

- Users: `GET/POST /api/admin/users`, `GET/PATCH /api/admin/users/{id}`. Generic PATCH cannot set role/password/identifiers. Create/import require admin/superadmin.
- Singular role: `PUT /api/admin/users/{id}/role {role}`. Admin may grant admin/operator/null only to non-superadmin targets; superadmin manages superadmin access. At least one active credentialed superadmin remains. Password provisioning `/users/{id}/password {password}` is superadmin-only.
- Definitions: `GET/POST /api/admin/training-types`, `PATCH /training-types/{id}`. Fields are name/icon_key/active, optional cached canvas_assignment_id/minimum_score and read-only sync diagnostics. Six icon choices are orientation, policies, 3d-printer, laser-cutter, resin-printer and waterjet. No slug/description/level.
- Person/source records: `GET/POST /api/admin/trainings`, optional user_id page filter; POST `{user_id,training_type_id,awarded_at?,expires_at?}`. `/trainings/{id}/revoke {reason}` revokes. DTOs include resolved user_name/href, training_type_name, has_training, source, award/expiry/revocation and current Canvas score/grade/passed/completed/fetched/submission/attempt fields. There is no certifications or separate result API.
- Visits: `GET /api/admin/visits`, `POST /visits/{id}/close {forgot_to_sign_out}`; active keyholder visits require handoff/closure first. `/keyholder-shifts` provides history/user links.
- Audit: `GET /api/admin/audit-events` returns Time/occurred_at, human action_label, actor_name/href, target_name/href and safe details. Internal UUIDs are not primary UI labels.
- Import: `/api/admin/imports/users/preview {csv_text}`, then `/apply {csv_text,fingerprint,confirm:true}`. Atomic revalidation creates only new users/identities, with no visits, prints, mail, passwords or role grants. Existing identities are not silently edited.

## Metrics and Canvas

Metrics `/api/admin/metrics` and `/metrics.csv` share start/end-exclusive/timezone filters, a consistent snapshot/captured clock and definitions. Summary includes attendance/unique/new visitors, finalized visit count/person-hours/average, open/excluded counts; daily series supports charts. Attendance includes overlapping open/forgotten visits; durations use closed non-forgotten clipped intervals. New visitors means first-ever visit. Each timestamptz stores one instant; lab boundaries/display use America/New_York with DST.

Canvas `/api/admin/canvas/status` returns configured/setup_message, per-training status and bounded unmatched/conflict summaries. `GET /api/admin/canvas/people` searches/pages the full cached roster using search, binding=unmatched|conflicts|all, page and page_size. Default binding is unmatched; default page size is 100, capped at 1000. It returns `{items,total,page,page_size}`; each person has id, display_name, email, canvas_id, user_id and conflict. The UI uses this endpoint rather than filtering the first 100 summary records locally. `POST /canvas/sync` accepts optional training_type_id and returns 202 queued/message or 409 already running. `/canvas/quizzes` returns cached `{items:[{id,title,points_possible}],refreshed_at}`; POST `/canvas/quizzes/refresh` queues a refresh. POST `/users/{id}/canvas-sync` attaches local cached evidence. Jobs use Procrastinate, hourly by default. Successful checkpoints advance only after complete fetch/application; there is no invented incremental timestamp parameter. See [schema](schema-proposal.md) for merged ownership/evidence and [status](status-report.md) for the successful authorized full read-only sync and its limits.

## Live printer and storage

Printing status is `GET /api/admin/printing/status {connected,busy,last_result}`. Last result is null or `{status:printed|failed|unknown,label_id,display_name,at,message?}`. POST `/api/admin/users/{id}/print` returns sent/offline/busy, optional label_id and message. Offline/busy drops; disconnect/timeout is unknown; no backlog/replay exists. Renderer dimensions remain 1109×696; original icons and full names replace tiers. Unit/wheel/simulated transport tests are not USB proof.

The superadmin `/admin/storage` UI calls `GET /api/admin/storage/objects?prefix=&cursor=&limit=`, POST the same route with one multipart `file`, and GET/DELETE `/api/admin/storage/object?key=`. Lists expose objects, reference users, next_cursor and upload_max_bytes. API operations are bounded at 5 MiB; nginx allows 6 MiB multipart overhead. Referenced-avatar deletion is 409 with human user references. Downloads are safe attachments, not rendered object content. S3/DB ports and credentials remain private; no vendor redirect/SSO or bucket IAM editor is claimed.

## SQL reads and held changes

Admin/superadmin can GET `/api/admin/database/tables`, `/rows?table=&page=&page_size=` and POST `/query {sql}`. There is no client mode/confirm-write field. Server parsing classifies reads versus DML. SELECT/EXPLAIN execute immediately in a database-enforced read-only restricted connection. Operators are denied; missing restricted URLs fail closed.

Superadmin supported writes return `{transaction_status:preview,preview_id,expires_at,table,operation,changes:[{before,after}],columns,rows,row_count,truncated,duration_ms}` from a real uncommitted transaction. POST `/preview/{preview_id}/commit` commits that held transaction; `/rollback` discards it. Both bind user/session and never rerun submitted SQL. Previews expire after 90 seconds; one per session/two globally, bounded rows/bytes/time, cleanup and shutdown rollback constrain resources. They may hold row locks while being reviewed.

Supported previews are INSERT VALUES and single-table UPDATE/DELETE. WITH writes, joined DML/UPDATE FROM/DELETE USING, INSERT SELECT, ON CONFLICT/UPSERT, primary-key changes, DDL and session/transaction commands are rejected. Credential/role/activation edits and user deletion use dedicated controls. Commit finalizes audit/revisions atomically; failure rolls back. Audit keeps digest/outcome rather than raw query literals/results. SQL grids scroll horizontally, support column visibility and hide id by default in normal multi-column browsing. This is bounded application SQL, not a cluster-superuser connection.


## Station/UI follow-up endpoints and semantics

Training type DTO/input/patch includes display_order>=0; all definition and badge sequences follow it. POST /api/admin/training-icons accepts one JPEG/PNG/WebP multipart file for admin/superadmin, normalizes to512px PNG in private S3, returns201 with icon_key/icon_url. GET /media/training-icons/<32hex>.png serves the intended public icon. Definition saves verify uploaded references; linked bucket deletion returns409.

GET /api/kiosk/state recent_activity includes enter_time/exit_time as well as action/occurred_at; only today's lab-local entered visits, latest10, are returned. Canvas status adds overview with genuine whole-job last_success_at/status/error. The UI uses one sync action and Canvas Users. GET /api/admin/trainings supports search by definition and human user name before paging/count.

GET /api/admin/storage/preview?key=&size= returns a re-encoded bounded raster only for superadmins; no arbitrary raw content or S3 URL. Generic upload API is retained for compatibility but has no storage-page form/Uploads section.

Metrics API retains canonical half-open bounds. UI dates are inclusive and fixed Eastern: metricsQueryParams adds one calendar day to the selected end for both JSON and CSV; filtersFromResponse subtracts it for display. Previous calendar month is the UI default. Same-day filters are valid; DST is handled server-side. No timezone control is exposed.
