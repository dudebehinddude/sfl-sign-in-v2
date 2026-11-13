# Local previews and later deployment preparation

No deployment workflow is enabled. CI checks/builds; local synthetic Compose is not a Zund deployment. No push, PR, merge, runner installation, production change or importer is authorized. [Feedback revision 3](feedback-revision-3.md) requires a new isolated schema; the `bb81f37` approval applies only to its prior baseline.

## Initialize a fresh local candidate

Use an ignored env file and the [README sequence](../README.md): choose APP_PORT/host/bind, supply local database/object-store secrets, start db/minio, run init-db/init-storage, bootstrap a university-email superadmin, then start the app. Bootstrap prompts for a password unless an explicit runtime password variable is supplied. `seed-demo` is an empty-database alternative with runtime DEMO_PASSWORD/prompt, synthetic 800000001/002/003 superadmin/admin/operator identities and no production credential.

`init-db` creates the fresh app plus Procrastinate schema. It does not migrate an old candidate or import production. API and worker share configuration; `python -m app.worker` runs the established queue library. Default Canvas interval is 3600 seconds. SMTP is currently explicitly disabled, including in the authorized real-read Canvas preview.

## Dev hot reload and isolation

The previous synthetic baseline remains on 8098. The feedback preview uses a separate env file with APP_PORT=8099:

```sh
pnpm compose --env-file .env.feedback --dev up --build -d
```

The helper adds compose.dev.yaml and the development frontend target/source mounts. Vite uses the selected public app port and proxies REST, WS and media to its own API. Without `--dev`, the normal web build serves static production assets through nginx. Keep the distinction when reporting which build was observed.

The helper derives `sfl-${APP_PORT}`, internal encoded DB URL, isolated networks/DB/object volumes and per-port cookie names, guarding against inherited shell overrides. Use it for every command. Do not reuse the baseline volume for the changed schema. No automatic command removes valuable volumes; never run down --volumes against an instance you need to preserve.

Loopback is default. Intentional LAN use needs APP_BIND_ADDRESS/APP_HOST and matching origin including port. LAN location does not grant staff access. DB, S3 API and vendor-console ports remain private; there is no external SQL-client port, tunnel or Adminer by default. One API process owns the ephemeral printer hub and SQL previews; scaling that model across processes is not established.

## Storage and SQL provisioning

The user-facing object browser is `/admin/storage`, superadmin-only, with app sessions/CSRF and no vendor login redirect. It manages the configured private S3 bucket through same-origin APIs. Object upload/download is bounded at 5 MiB; nginx allows 6 MiB multipart overhead. Intended avatars are reencoded/served through the app, and referenced avatars cannot be deleted in the object browser. This is not an access-key/IAM/server-config console.

The underlying S3-compatible service remains the existing pinned MinIO build; no storage engine migration was selected. Its maintenance and alternative-engine research remain a production decision. Current Compose passes configured object-store credentials to the adapter; settle least-privilege bucket-scoped credentials, backup/restore and restart persistence before rollout. Do not expose S3 directly or reuse one engine's raw volume with another.

SQL requires explicitly provisioned restricted LOGIN roles/URLs. Use console-role-names, configured SQL_READ_DATABASE_URL/SQL_WRITE_DATABASE_URL and init-console-roles. Missing URLs fail closed; arbitrary SQL never uses the app-owner connection. Admin reads only; SA writes use a real 90-second held preview, one per session/two globally, with exact Commit/Roll back and bounded output/locks. DDL, write joins, UPSERT and protected account changes are unsupported through this interface.

## Evidence before any adoption

See [status](status-report.md) and the primary [verification log](verification-log.md) for actual runs. The final revision passes 156 backend tests on host and Python 3.13 image, 83 frontend tests, lint/typecheck and the production build. All 47 printer tests and 5 Compose-helper checks pass; storage adapter/UI checks are included in those totals. Seven actual Chromium sizes and the SQL/storage/roles/registration/Canvas workflows pass, including 480×320 registration. Sol and Composer approved in two rounds each. This is local verification, not remote CI or a production rollout. Do not reuse old 8098 results as proof of the changed revision.

Canvas token use was explicitly authorized for read-only course/catalog/submission checks only. Course access/catalog/submission fields and a full read-only sync are verified. After the enrollment-state fix, the sync cached 2503 people and 14796 training rows across six training types. SMTP is disabled and USB has never printed; backup/restore, production performance/parity and the real importer remain later work.

## Future self-hosted runner

After user review and deployed-source/database/media reconciliation, plan a repository-scoped runner, protected deployment environment/manual approval, immutable image tags, DB/object backup, reviewed migrations and an isolated beta smoke test before switching traffic. Keep production credentials on the target host and untrusted PR jobs off production-connected runners. Define rollback across compatible images/schema/object state. Do not implement or activate rollout merely because this plan exists.


## Existing local candidate upgrade

Before running this post-a133323 source against an existing preview database, apply backend/migrations/add_training_display_order.sql to that intended instance. It adds/backfills the order column and CHECK without deleting user/Canvas/training rows, and reapplication preserves later custom ordering. The primary applied it only to8099 and verified counts unchanged. This is not authorization or a complete importer for production. Training icon media now lives in the configured S3 bucket; preserve that volume together with PostgreSQL.
