# Revised schema proposal

The [feedback revision 3](feedback-revision-3.md) instructions supersede older proposals. This is the implemented local candidate for user review, not an approved production schema or importer. Compare the [old repository schema](research/legacy-schema.md); GitHub does not describe all unpublished Zund changes.

## People, identity and authorization

| Table | Meaning and important fields |
| --- | --- |
| `users` | UUID id; names; one canonical nullable university email; nullable password_hash/avatar_key; one nullable role; numeric space_level; numeric keyholder_priority; active; creation/update times. |
| `external_identities` | UUID id; provider/issuer/value unique source identity; nullable local user binding; verification/freshness metadata. A Canvas identity may predate local signup. |
| `auth_sessions` | Hashed opaque cookie token, owning user, CSRF state, expiry/revocation. |
| `password_resets` | Hashed single-use recovery token, owning user, expiry/used time. |
| `login_attempts` | Bounded login/recovery rate-limit evidence. |

`users.role` is a real PostgreSQL enum and Python enum with superadmin/admin/operator, or null for no staff role. There is no viewer or `user_roles` table. Physical access is separate: `space_level` member=0, volunteer=1, keyholder=2, staff=3, represented by Python IntEnum and PostgreSQL integer CHECK. Priority has minimum/default -1.

User-entered email accepts charlotte.edu/uncc.edu case-insensitively and maps the alias once on write. There is no raw/normalized duplicate. Cached Canvas roster email is its own external source attribute, not a second local user email. Conflicting ownership or ambiguous matches require review and never silently rebind identities. Credentialed recovery-email changes require owner/superadmin and invalidate pending links/mail. Normal DTOs and SQL reader privileges exclude password hashes.

## Training definitions and merged records

| Table | Meaning and important fields |
| --- | --- |
| `training_types` | id, name, icon_key, active, nullable cached canvas_assignment_id/minimum score, successful sync start/completion/error and timestamps. No slug, description or training level. |
| `canvas_quizzes` | Cached real assignment ID, friendly title, possible points and fetch time. The UI calls these Canvas quizzes; the fetch path needs assignment IDs. |
| `canvas_roster` | Cached external person/name/email, one external_identity_id, freshness and matching-conflict diagnostics. |
| `trainings` | Definition; source; exclusive ownership; accepted award/expiry/revocation; latest score/grade/passed/workflow/submission ID/attempt/completed/fetched fields; configuration fingerprint; timestamps. |

There is no `canvas_results` or certifications table. Manual training rows store user_id and no external identity. Canvas rows store external_identity_id and no user_id; their current local owner resolves through that identity. A source/owner CHECK prevents two independent binding authorities. The Canvas identity/type pair is unique, so regrades update current evidence rather than appending duplicate source rows. Manual assignment uses the existing user lock and rejects a second active, unexpired manual row; revoked or expired history can be reassigned. DTOs may expose the resolved user_id for navigation; that is not a second stored ownership field.

An external result can be cached before signup with no awarded_at. Passing evidence grants a training only after binding, current configuration and eligibility are checked. Awarded state is distinct from latest passed/score/grade: a later nonpassing/missing result or failed fetch does not silently revoke an earned award. Revoked awards are not resurrected. Independent manual rows survive Canvas refresh. `has_training` is a derived response value, not a stored training tier.

Configuration fingerprints include the actual source selection/threshold and interpretation settings. Definition changes invalidate stale interpretation/checkpoints. Successful start and completion checkpoints advance only after complete fetch, validation and application; fetch time is not fabricated source completion time.

All trainings use the paginated assignment-submissions path recovered from newer source. The current endpoint has no invented incremental `since` filter. Hourly scheduling defaults to 3600 seconds. Roster fetching now includes all five supported enrollment states; unresolved submission owners are skipped/counted, never made into an ownership authority. See [status](status-report.md) for the successful authorized full read-only sync and its aggregate counts.

## Visits, shifts and reports

| Table | Rules |
| --- | --- |
| `visits` | user_id, enter_time, nullable exit_time, forgot_to_sign_out and timestamps. One open visit per person; exit cannot precede entry. |
| `keyholder_shifts` | responsible user, started_at/ended_at and timestamps. At most one active shift. |
| `audit_events` | Immutable meaningful action/actor/target/time and safe details; readable API labels/links are projections. |
| `scope_revisions` | Public/staff counters locked through commit; notifications trigger authoritative refresh. |

Duration is computed from exit_time minus enter_time, with no mutable duplicate total. A generated stored interval remains a valid later optimization if measured. Reports still clip intervals to their half-open date window. Attendance counts overlapping open/forgotten visits; finalized hours/averages use closed non-forgotten intervals; new visitors are first-ever visits. Charts/CSV share a consistent snapshot and captured clock.

Every timestamp stores one PostgreSQL timestamptz instant. SQL display, UI and report date boundaries use America/New_York, including EST/EDT. There are no paired UTC/local columns. Mutable application rows have database creation/update defaults and update triggers; these do not reconstruct missing historical facts.

Existing keyholder behavior remains: volunteer+ opening/handoff, arriving keyholder+ takeover only with strictly greater priority, and atomic departure/handoff/closure. A lab transaction lock and one-open constraints protect transitions. Registration explicitly carries its identifier; expected_shift_id rejects stale keyholder decisions. No device/intent/receipt/idempotency tables are added, and clients do not replay an uncertain toggle.

## Objects, printing and background infrastructure

Users hold avatar_key only; bytes/metadata live in the configured private S3 bucket. There is no files table. `/admin/storage` manages objects through superadmin-only app routes, without vendor redirect or public S3 ports. Object operations are bounded at 5 MiB, with 6 MiB nginx multipart allowance; referenced avatars cannot be deleted through the object browser.

Printing is a single live subscriber, not a table or queue. Its payload is display_name plus badges containing training_type_id/name/icon_key. The original six PNGs are packaged unchanged; the renderer draws full names in monochrome without tiers. Attendance commits/responds before dispatch. Offline/busy sends drop; disconnect/timeout means unknown; reconnect never replays.

Procrastinate owns scheduled Canvas/email/expiry work in its jobs schema. `email_jobs` holds private delivery state/payload only until delivery/cancellation; it is not the scheduling engine. No application scheduled_jobs, sync_runs, mappings or durable change-event table remains. SMTP and printer network I/O stay outside the tap transaction.

## Later production mapping

The user will supply deployed source, database and media later. Map legacy physical values 0/30/70/100 to 0/1/2/3 and every negative priority to -1, preserve real timestamps, and report identity/enum exceptions. The fixed swapped Canvas/Niner-ID incident is a migration regression, not an active bug. No missing history, live parity or production importer is invented here.

Current definitions: [models](../backend/app/models.py), [schemas](../backend/app/schemas.py), [OpenAPI](../backend/openapi.json), [API contract](api-contract.md).


## Later training icon/order correction

Training types also store nonnegative display_order, default100 for new appended types, with the six original sticker positions0–5 seeded explicitly. Canonical ordering is display_order,name,id. Icon is an uploaded image key such as training-icons/<uuidhex>.png, with bytes in S3 only; six legacy named keys remain a migration fallback. New UI definitions upload first. No file metadata table was added. The additive SQL in backend/migrations preserves existing data and is not a production importer.
