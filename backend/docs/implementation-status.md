# Backend implementation status, feedback revision 3

This implements [feedback items 1–17](../../docs/feedback-revision-3.md) after the approved local `bb81f37` baseline. Its scoped Sol/Composer reviews are approved; final user architecture/schema acceptance remains separate. Existing databases require deliberate later migration; no production connection/import, push or rollout occurred.

## Domain and authority

Users have one nullable native PostgreSQL/Python enum role: superadmin/admin/operator. There is no viewer, user_roles or accounts table. Physical space_level is independently constrained to integer 0–3; priority minimum/default is -1. User-entered registration/account/profile/recovery/import emails accept only charlotte.edu/uncc.edu, canonicalizing case/alias once. External identity provider/issuer/value has one nullable local owner. Password hashes stay on users and outside normal DTO/SQL-reader visibility.

Operator reads most domain/audit data and may assign/revoke trainings and edit basic names/contact fields, with credentialed recovery-email ownership protection. Operator cannot create/import identities or edit access/priority/active/role/security. Admin additionally administers domain data and non-superadmin roles, with SQL reads only. Only SA changes superadmin access, provisions passwords, manages stored objects and stages SQL writes. Last active credentialed SA removal is blocked. Integration secrets remain environment configuration.

Normal lists default to 100 and cap at 1000. User/audit projections batch human names; audit response has action_label/actor_name/href/target_name/href and safe details. Product UI does not expose raw permission catalogs or UUIDs as primary labels.

## Training and Canvas

Training definitions contain name/icon_key/active, cached assignment ID/score threshold and successful sync diagnostics. Icon input is limited to the six original keys. There is no definition slug/description/level. Public badge fields are training_type_id/name/icon_key only.

`trainings` holds manual rows with user_id only or Canvas rows with external_identity_id only. A CHECK prevents duplicate ownership authority; Canvas identity/type is unique. Local ownership is resolved through the canonical external identity, including pre-signup cache. No certifications or canvas_results table remains. Nullable awarded_at tracks accepted earned state separately from current passed/score/grade/submission/attempt/completed/fetched evidence and fingerprint. Matching/current-config checks protect new awards; missing/nonpassing/failed refresh does not silently revoke earned history, revoked rows are not resurrected, and manual rows remain independent.

One fully paginated assignment-submissions path supports the recovered bulk design. Cached quiz choices include classic/external-tool assignments and store the actual assignment IDs. Successful checkpoints update only after complete valid fetch/application; no unsupported since parameter is invented. Hourly sync defaults to 3600 seconds; Procrastinate dispatch/retry/locking remains in its own jobs schema, without custom run/history tables.

Authorized GET-only real access established course 231237 Teacher role, 26 catalog assignments and submission ID/attempt. After correcting the historical roster enrollment-state request, the full read-only sync succeeded with 2503 cached people, 14796 training rows and six training types. Fetch includes active/invited/rejected/completed/inactive and counts/skips unresolved submission owners instead of inventing binding authority. SMTP is explicitly disabled and no real email was sent.

## Attendance, live state and time

Visits use enter_time/exit_time/forgot_to_sign_out; duration is computed. One-open visit/shift constraints, lab locking and existing volunteer/priority/handoff/closure semantics remain. The internal kiosk has no pairing/device/intents/receipts; registration carries identifier and keyholder decisions expected_shift_id. Clients serialize commands and refresh after uncertain replies, never replaying a toggle. No Canvas/SMTP/printer I/O happens inside tap transactions.

Public/staff revision locks order commit notifications. Public DTOs contain intended names/photos/completed icon badges, without student/Canvas IDs, emails or admin controls. Private streams reauthorize roles/sessions and reconnect takes authoritative snapshots. Printing is one live subscriber: offline/busy drop, ephemeral ID/ack, unknown output after lost acknowledgment, no persistent queue/reconnect replay. Attendance commits/responds before dispatch. Printer raster/protocol/wheel proof is not physical USB proof.

Every timestamptz represents one instant. PostgreSQL session display, UI and report boundaries use America/New_York with DST. Reports share one captured clock/consistent snapshot across summary/daily/CSV, clip half-open intervals and exclude open/forgotten visits from finalized hours while counting their attendance. Timestamp defaults/update triggers apply to mutable rows; missing imported history is not fabricated.

## SQL reads and transaction previews

POST `/api/admin/database/query` accepts only `{sql}`. Server parsing classifies the statement; no mode/confirm-write dropdown or body exists. Admin/SA SELECT/EXPLAIN executes immediately in actual restricted read-only transactions. Operator is denied; missing separate SQL URLs fail closed. Owner connections never execute submitted SQL; password hashes and private recovery mail are not reader-visible.

SA INSERT VALUES or single-table UPDATE/DELETE stages a real held restricted writer transaction and returns exact before/after changes, preview_id/expiry/table/operation and bounded results. Commit/Roll back binds both actor and authenticated session. Commit finalizes the existing transaction without re-executing SQL, with atomic audit/revision invalidation; finalization failure rolls back. Ninety-second expiry, one pending per session/two globally, cleanup/shutdown rollback and resource caps bound holds. UPDATE/DELETE lock bounded preimages without holding lab/revision locks during human review; concurrent predicate additions cause rollback instead of an invented diff.

WITH writes, joined DML/UPDATE FROM/DELETE USING, INSERT SELECT, ON CONFLICT/UPSERT, primary-key changes, DDL and session/transaction control are unsupported. Credential/role/activation edits and deleting users use dedicated account controls. SQL defaults to and caps at 1000 result rows, uses a default 5000 ms statement timeout and caps response/cell bytes. Audit records digest/outcome rather than raw SQL/results. This is bounded application SQL, not PostgreSQL cluster-superuser access.

## S3 objects and setup

Users store avatar_key only; intended avatars are validated/reencoded in private S3. SA `/api/admin/storage/objects` lists/uploads, and `/object?key=` downloads/deletes. Streams/keys are bounded/validated, downloads are attachments and referenced avatars return 409 before deletion. API file bound is 5 MiB, nginx multipart ceiling is 6 MiB. In-app `/admin/storage` replaces the vendor-console redirect; no S3 host port, IAM/secret editor or storage-engine switch is introduced.

`init-db` creates a fresh app/library jobs schema; init-storage creates the configured bucket. Console-role-names/init-console-roles provision explicit restricted SQL logins. Bootstrap requires valid university email/identifier and runtime password. Seed-demo refuses nonempty users and uses synthetic 800000001/002/003 SA/admin/operator identities with a runtime password, never production defaults. Export-openapi regenerates the wire schema. The helper `--dev` overlay runs the separate 8099 Vite/API/WS feedback preview while preserving prior 8098 fixtures.

## Verification boundary

The final host-PostgreSQL run passed all 156 backend tests without skips in 22.19 seconds, with Ruff checks/formatting clean across 53 Python files. Primary observed 83 frontend tests across 25 files, lint/typecheck and a successful production build. Storage passed 21 PostgreSQL/fake-S3 tests and 8 frontend tests included in the 83. Printer checks passed 47 tests with raster/wheel proof; the Compose helper passed 5. Seven Chromium viewport checks pass, including 480×320 registration. Actual SQL preview/commit/rollback, local Monaco, scrollable grids, storage CRUD, named audit links, roles, university registration, original icon tooltips and full-cache Canvas pagination pass. The final Python 3.13 image passes all 156 backend tests without skips in 23.03 seconds. Final commands/counts belong in the primary [verification log](../../docs/verification-log.md).

The successful read-only real Canvas sync does not prove SMTP, USB, production parity/performance or migration. Primary Sol round2 approved the final changed contracts; Composer round2 approved its scoped correction. These are new feedback-task reviews, not inherited baseline approval. No student names/emails, credentials, tokens or private source payloads are included in this report.
